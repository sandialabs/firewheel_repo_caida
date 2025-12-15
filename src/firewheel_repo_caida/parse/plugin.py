import os
import gzip
import contextlib
from itertools import product

import netaddr
from caida.parse import ASAnnotation
from base_objects import Switch
from generic_vm_objects import GenericRouter

from firewheel.control.experiment_graph import Edge, Vertex, AbstractPlugin

current_module_path = os.path.abspath(os.path.dirname(__file__))
aslinks_default = os.path.join(current_module_path, "cycle-aslinks.txt.gz")
bgp_table_default = os.path.join(current_module_path, "routeviews.gz")


class ParseCAIDA(AbstractPlugin):
    """
    This imports a CAIDA AS trace into the graph.

    This will walk through the CAIDA trace files and create a BGP router
    for each AS number. Any links in the traces will be placed into the
    graph appropriately.

    The attributes that it sets in the graph vertices are as follows:

    Router:
        - **type** - Always set to ``"router"``
        - **as** - The router's AS number
        - **interfaces** - The active interfaces for the router
        Format: ``{ <NUM>: { 'netmask', 'name', 'address' } }``
        - **bgp** - The BGP neighbor information for this router
        Format: ``{ <NUM>: { 'as', 'address' } }``
        - **bgp_networks** - the networks to be explicitly advertised by BGP
        Format: ``{ <NUM>: { 'netmask', 'address' } }``
        - **new** - Indicates that this is a new device and needs to be processed
        by the other plugins. (It is set to :py:data:`True`)

    Link:
        - **new** - Indicates that this is a new device and needs to be processed
        by the other plugins. (It is set to :py:data:`True`)
    """

    def run(self, aslinks=aslinks_default, bgp_table=bgp_table_default):
        """
        Parse the given CAIDA information into a BGP network used for a FIREWHEEL experiment.
        The method generates AS links, assigns BGP networks, and removes OSPF information.

        Args:
            aslinks (str): The AS links file to parse and import. This should be
                a gzipped file in the format provided by CAIDA. An example
                filename would be ``cycle-aslinks.l7.t3.c006830.20180719.txt.gz``.
            bgp_table (str): The file mapping AS numbers to IP networks. This
                should be a gzipped file in the format provided by CAIDA. An
                example filename would be ``routeviews-rv2-20180731-1200.pfx2as.gz``.
        """
        self.vertices = {}
        self.link_attrs = {}

        # We need to be able to build a subnet tree to keep track of the
        # AS' networks
        self.tree = Vertex(self.g)
        self.tree.decorate(ASAnnotation, init_args=["ANNOTATION_subnet_tree"])

        # First the AS map with links will be built, and then the
        # appropriate BGP networks will be assigned
        self.log.debug("Generate AS links")
        self.generate_as_links(aslinks)

        # Then, assign the appropriate BGP network to every needed BGP
        # router
        self.log.debug("Assign BGP networks")
        self.assign_bgp_networks(bgp_table)

        # Remove all OSPF information
        self.log.debug("Strip OSPF info")
        self.remove_ospf_info()

    def generate_as_links(self, aslinks):
        """
        Generate the appropriate links between ASes in the graph.

        Args:
            aslinks (str): The AS links file to parse and import.
        """
        if aslinks.endswith(".gz"):
            with gzip.open(aslinks, "rt") as linkstream:
                data = linkstream.read()
        else:
            with open(aslinks, "r", encoding="utf-8") as linkstream:
                data = linkstream.read()

        for line in data.splitlines():
            if line[:1] == "D" or line[:1] == "I":
                # This is a direct link, process it
                self.process_direct_link_line(line)

    def process_direct_link_line(self, line):
        """
        Process a direct link input line

        This line takes the form::

             D    from_AS    to_AS   monitor_key{i}   ...

        We are only interested in ``from_AS`` and ``to_AS`` at this point.  This
        function will take this line and make sure that both ``from_AS`` and
        ``to_AS`` exist as vertices, and then create a link between them if
        such a link doesn't exist.

        This method also connects all nodes to a giant "control network" via the
        ``SWITCH_BGP_CONTROL`` :py:class:`Switch <base_objects.Switch>`. This will
        later be pruned off in :ref:`caida.prune_routers <caida.prune_routers_mc>` but
        will enable keeping a slightly larger subset of the BGP topology during the pruning.
        For example, using the July 2018 data we ran:
        ``firewheel experiment caida.test_topology caida.prune_routers`` both
        with ``SWITCH_BGP_CONTROL`` and without. The resulting graph without the switch had
        53 Nodes and 165 Edges while the graph *with* the switch contained
        64 Nodes and 396 Edges.

        This implementation currently does not handle the case where an AS may
        have multiple networks associated with it. The linking logic assumes
        a single BGP connection between two routers, which may not accurately
        represent the topology in scenarios involving multi-origin AS (MOAS)
        or multiple networks.

        Args:
            line (str): The line from the AS links file representing a direct link.
        """  # noqa: DOC501
        try:
            line += " a b c  d"
            (d, from_ases_str, to_ases_str, _mons) = line.split(None, 3)
            if d not in {"D", "I"}:
                raise RuntimeError("Not direct link")

            from_ases = self._get_AS_list(from_ases_str)
            to_ases = self._get_AS_list(to_ases_str)

        except (RuntimeError, ValueError) as e:
            self.log.exception("Line in wrong format: %s", e)
            return

        # Now, for each link, we need to add the appropriate link in the graph
        for from_as, to_as in product(from_ases, to_ases):
            from_name = self._get_AS_name(from_as)
            to_name = self._get_AS_name(to_as)

            # First, check if this has already been processed
            if (from_name, to_name) in self.link_attrs or (
                to_name,
                from_name,
            ) in self.link_attrs:
                continue

            # Add a link to the special BGP control plane
            switch_name = "SWITCH_BGP_CONTROL"
            # Create the switch
            try:
                switch = self.vertices[switch_name]
            except KeyError:
                self.vertices[switch_name] = Vertex(self.g, switch_name)
                switch = self.vertices[switch_name]
                switch.netplane = 0
                switch.decorate(Switch)

            # And add in the neighbor details
            # We don't have the IP address yet, so we won't add that in
            try:
                self.vertices[from_name]
            except KeyError:
                from_vm = Vertex(self.g, from_name)
                from_vm.decorate(GenericRouter)
                self.vertices[from_name] = from_vm

            try:
                self.vertices[to_name]
            except KeyError:
                to_vm = Vertex(self.g, to_name)
                to_vm.decorate(GenericRouter)
                self.vertices[to_name] = to_vm

            # Make a 'false' link between the two
            self.link_attrs[from_name, to_name] = Edge(
                self.vertices[from_name], self.vertices[to_name]
            )
            self.link_attrs[from_name, to_name].false = True

            self.control_net_hosts = getattr(self, "control_net_hosts", None)
            if self.control_net_hosts is None:
                try:
                    self.control_net_hosts = switch.network.iter_hosts()
                except AttributeError:
                    control_net = netaddr.IPNetwork("10.192.0.0/10")
                    switch.network = control_net
                    self.control_net_hosts = switch.network.iter_hosts()

            # Make links to the switch
            netmask = switch.network.netmask
            _iface_name, _edge = self.vertices[from_name].connect(
                switch, next(self.control_net_hosts), netmask
            )
            _iface_name, _edge = self.vertices[to_name].connect(
                switch, next(self.control_net_hosts), netmask
            )

            # We need to fill in these details both here and in
            # processing BGP networks because it's possible ASes may
            # not have neighbors or may not have networks
            with contextlib.suppress(AttributeError):
                self.vertices[from_name].set_bgp_as(from_as)
                self.vertices[to_name].set_bgp_as(to_as)
                # This method sets up the BGP information on both vertices.
                self.vertices[from_name].link_bgp(
                    self.vertices[to_name], switch, switch
                )

    def assign_bgp_networks(self, bgp_table):
        """
        Assign the given BGP networks to each AS.

        Args:
            bgp_table (str): The file mapping AS numbers to IP networks.
        """
        if bgp_table.endswith(".gz"):
            with gzip.open(bgp_table, "rt") as tablestream:
                data = tablestream.read()
        else:
            with open(bgp_table, "r", encoding="utf-8") as tablestream:
                data = tablestream.read()

        for line in data.splitlines():
            self.process_bgp_table_line(line)

        tablestream.close()

    def process_bgp_table_line(self, line):
        """
        Process the given line in the BGP table by adding the BGP networks to the appropriate
        ASes in the graph.

        This line takes the form::

            network     cidr        AS

        Note:
            Currently, multi-origin AS (MOAS) isn't supported, so if this is the case
            then the first entry is chosen.

        Args:
            line (str): The line from the BGP table representing a network, CIDR, and AS.

        Raises:
            ValueError: If the line in the BGP table is malformatted.
        """
        try:
            (net, cidr, as_str) = line.split()

            network = netaddr.IPNetwork("%s/%s" % (net, cidr))
            ases = self._get_AS_list(as_str)

            # At the moment, multi-origin AS (MOAS) isn't supported, so return the first AS
            ases = [ases[0]]

        except Exception as exc:
            raise ValueError("Poorly formatted BGP table line: %s" % exc) from exc

        # Check if this network has already been processed
        if self.tree.is_network_in_tree(network):
            return

        for autosys in ases:
            # Now, add this network to the AS
            as_name = self._get_AS_name(autosys)

            try:
                vertex = self.vertices[as_name]
            except KeyError:
                # self.log.warning('%s has no links', as_name)
                continue

            # Add in this new network
            vertex.add_bgp_network(network)

            # Now, build the switch for the new BGP network.
            # Do this now so we can add a complete record to the subnet tree
            # annotation.
            bgp_net_hosts = network.iter_hosts()

            bgp_net_switch = self._get_bgp_net_switch(network)
            if bgp_net_switch not in self.vertices:
                self.vertices[bgp_net_switch] = Vertex(self.g)
                self.vertices[bgp_net_switch].decorate(
                    Switch, init_args=[bgp_net_switch]
                )
            switch = self.vertices[bgp_net_switch]
            switch.network = network
            switch.skip_create_network = True

            # Form the edge between the switch and the router.
            try:
                vertex.connect(switch, next(bgp_net_hosts), network.netmask)
            except StopIteration:
                # Add the AS to the subnet tree either way.
                self.log.warning("Unable to fit router on %s, skipping", network)

            # Finally, add this AS and network to the subnet tree
            self.tree.add_subnet(network, as_name, switch)

    def _get_AS_list(self, as_str):  # noqa: N802
        """
        Return a list of the ASes referenced, including multi-origin AS (MOAS) and sets.

        The CAIDA syntax for MOAS is ``X_Y_Z``, and the syntax for sets is
        that they are comma separated. This method separates each AS number
        as if they were independent (effectively ignoring MOAS).

        Args:
            as_str (str): The string representing AS numbers.

        Returns:
            list: A list of AS numbers.
        """
        ases = []
        for asblock in as_str.split("_"):
            for autosys in asblock.split(","):
                ases.append(autosys)  # noqa: PERF402

        return ases

    def _get_AS_name(self, as_number):  # noqa: N802
        """
        Return the AS name in the graph for the given AS number.

        Args:
            as_number (str): The AS number.

        Returns:
            str: The AS name in the graph.
        """
        return "router.AS%s.as.net" % as_number

    def _get_switch_name(self, from_as, to_as):
        """
        Return the switch name in the graph for the given link.

        Args:
            from_as (str): The AS number of the source.
            to_as (str): The AS number of the destination.

        Returns:
            str: The switch name in the graph.
        """
        return "SWITCH_%s_%s" % (from_as, to_as)

    def _get_bgp_net_switch(self, net):
        """
        Return the canonical switch name for the given BGP network.

        Args:
            net (IPNetwork): The BGP network.

        Returns:
            str: The canonical switch name for the BGP network.
        """
        return "BGP-" + str(net.cidr).replace(".", "-").replace("/", "-")

    def remove_ospf_info(self):
        """
        Set all OSPF parameters to None.
        """
        for vertex in self.vertices:
            self.vertices[vertex].bgp_over_ospf_redistribution = None
            self.vertices[vertex].ospf_over_bgp_redistribution = None
            self.vertices[vertex].ospf = None
