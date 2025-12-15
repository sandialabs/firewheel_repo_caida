import json
from pprint import pprint

from netaddr import IPNetwork
from base_objects import Switch, VMEndpoint
from generic_vm_objects import GenericRouter

from firewheel.control.experiment_graph import Vertex, AbstractPlugin


class Load(AbstractPlugin):
    """
    Load a CAIDA network topology from a JSON file and process its vertices.
    """

    def run(self, filename):
        """
        Load a CAIDA network topology from a JSON file and process its vertices.
        The JSON file should be created via the :ref:`caida.save_mc`.
        Populates the `self.switches` and `self.routers` dictionaries per the topology
        and configures BGP for routers in a second pass over the data.

        Args:
            filename (str): The path to the JSON file containing the topology data.

        Raises:
            TypeError: If the filename is not provided.
        """
        if not filename:
            raise TypeError(
                "Must provide a filename to ``caida.load`` for the JSON input."
                "This should be the output of ``caida.save``."
            )

        with open(filename, "r", encoding="utf-8") as json_topology:
            topology = json.load(json_topology)

        topology = topology["vertices"]

        self.switches = {}
        self.routers = {}

        for vtx in topology:
            if "name" not in vtx:
                print("Unable to load JSON vertex with no name:")
                pprint(vtx)
                continue

            if "type" not in vtx:
                print("Unable to load JSON vertex with no type:")
                pprint(vtx)
                continue

            if vtx["type"] == "host":
                self.handle_host(vtx)
            elif vtx["type"] == "router":
                self.handle_router(vtx)
            else:
                print(f"No load handler for vertex of type: {vtx['name']}")
                pprint(vtx)

        # Need all routers created before BGP is configured.
        # This forces a second pass over the data
        for vtx in topology:
            if "type" in vtx and vtx["type"] == "router":
                self.handle_bgp(vtx)

    def handle_host(self, vtx):
        """
        Creates a host vertex in the graph and adds its interfaces.

        Args:
            vtx (dict): The vertex dictionary containing host information.
        """
        host = Vertex(self.g, vtx["name"])
        host.decorate(VMEndpoint)

        try:
            self.add_interfaces(host, vtx["interfaces"])
        except KeyError:
            print(f"No interfaces for host: {host.name}")

    def add_interfaces(self, vertex, interfaces):
        """
        Connects the vertex to switches in the graph based on the interface data.

        Args:
            vertex (Vertex): The vertex to which interfaces will be added.
            interfaces (list): A list of interface dictionaries.
        """
        if not interfaces:
            print(f"No interfaces found for vertex: {vertex.name}")
            print("NOT able to connect it into the graph.")

        for interface in interfaces:
            switch = self.get_switch(interface["switch"])
            vertex.connect(switch, interface["address"], interface["netmask"])

    def handle_router(self, vtx):
        """
        Creates a router vertex in the graph, adds its interfaces, and sets up BGP if specified.
        This method currently does not handle OSPF links, which will need to happen prior to BGP
        so that it can properly advertise the BGP links.

        Args:
            vtx (dict): The vertex dictionary containing router information.
        """
        router = Vertex(self.g, vtx["name"])
        router.decorate(GenericRouter)

        self.routers[router.name] = router

        self.add_interfaces(router, vtx["interfaces"])

        # Can't link BGP routers without AS set, so it has to be
        # done in the first pass
        if "routing" not in vtx or "bgp" not in vtx["routing"]:
            return

        if (
            "parameters" not in vtx["routing"]["bgp"]
            or "router-as" not in vtx["routing"]["bgp"]["parameters"]
        ):
            print(f"BGP Router does not have AS number: {router.name}")
            return

        router.set_bgp_as(vtx["routing"]["bgp"]["parameters"]["router-as"])

    def handle_bgp(self, vtx):
        """
        Sets up BGP networks and neighbors for a router vertex.

        Args:
            vtx (dict): The vertex dictionary containing BGP configuration.
        """
        if vtx["name"] not in self.routers:
            print(f"No router named: {vtx['name']}")
            return

        router = self.routers[vtx["name"]]

        try:
            bgp = vtx["routing"]["bgp"]
        except KeyError:
            return

        try:
            for network in bgp["networks"]:
                router.add_bgp_network(IPNetwork(network))
        except KeyError:
            # Not all BGP routers advertise their own networks
            pass

        try:
            for peer in bgp["neighbors"]:
                switch = self.get_switch(bgp["neighbors"][peer])

                if peer not in self.routers:
                    print(f"Cannot find BGP peer: {peer}")
                    continue

                router.link_bgp(self.routers[peer], switch)
        except KeyError:
            pass

    def get_switch(self, switch_name):
        """
        Adds the switch to the `self.switches` dictionary if it is newly created.

        Args:
            switch_name (str): The name of the switch.

        Returns:
            Vertex: The switch vertex.
        """
        if switch_name not in self.switches:
            # If it isn't in the cache, then it is unlikely
            # that it is in the graph, but in case this plugin
            # gets chained in unexpected ways, be safe and check
            switch = self.g.find_vertex(switch_name)
            if not switch:
                switch = Vertex(self.g, switch_name)
                switch.decorate(Switch)

            self.switches[switch_name] = switch
            return switch
        return self.switches[switch_name]
