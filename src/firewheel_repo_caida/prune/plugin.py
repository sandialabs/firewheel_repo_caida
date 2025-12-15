import netaddr
from base_objects import Switch
from generic_vm_objects import GenericRouter

from firewheel.control.experiment_graph import AbstractPlugin


class PruneCAIDA(AbstractPlugin):
    """
    Removes all routers that aren't in a shortest path.

    Note:
        This plugin uses NetworkX directly to compute shortest paths.
    """

    def run(self):
        """
        Finds and removes all routers that aren't in a shortest path.

        This method performs the following steps:
        1. Weights edges and removes specific edges.
        2. Removes all coloring from vertices.
        3. Finds shortest paths and colors vertices in those paths.
        4. Restores deleted edges.
        5. Removes non-colored routers and switches.
        6. Cleans up interfaces, BGP neighbors, and advertised networks.
        7. Collects next hop IP addresses and removes unused BGP interfaces.
        """
        self.weight_and_remove_edges()
        self.remove_coloring()
        self.find_and_color_shortest_paths()
        self.restore_deleted_edges()
        self.prune_non_colored_nodes()
        self.clean_up_interfaces_and_bgp_neighbors()
        self.remove_unused_bgp_interfaces()

    def weight_and_remove_edges(self):
        """
        Weights edges and removes specific edges.
        """
        counter = 0
        self.log.debug("Weighting %d edges.", len(list(self.g.get_edges())))
        to_delete = []
        for edge in self.g.get_edges():
            if edge is None:
                continue
            if (
                edge.source.type == "annotation"
                or edge.destination.type == "annotation"
            ):
                continue
            counter += 1
            try:
                if (
                    edge.source.name == "SWITCH_BGP_CONTROL"
                    or edge.destination.name == "SWITCH_BGP_CONTROL"
                ):
                    to_delete.append(edge)
            except AttributeError:
                pass
        for edge in to_delete:
            edge.delete()
        self.log.debug("Added weights to %d edges.", counter)
        self.to_delete = to_delete

    def remove_coloring(self):
        """
        Removes all coloring from vertices.
        """
        host_count = 0
        router_count = 0
        for vertex in self.g.get_vertices():
            vertex.colored = False

            if vertex.is_decorated_by(GenericRouter):
                router_count += 1
            if (
                not vertex.is_decorated_by(GenericRouter)
                and not vertex.is_decorated_by(Switch)
                and not vertex.type == "annotation"
            ):
                host_count += 1

        self.log.debug("\t> prune caida: %d hosts/%d routers", host_count, router_count)

    def find_and_color_shortest_paths(self):
        """
        Finds shortest paths and colors vertices in those paths.
        """
        self.log.debug("\t=> finding shortest paths: ")
        host_filter = (  # noqa: E731
            lambda vertex: (not vertex.is_decorated_by(GenericRouter))
            and (not vertex.is_decorated_by(Switch))
            and (not vertex.type == "annotation")
        )

        def path_action(source, dest, path):
            for vert in path:
                vert.colored = True
            source.colored = True
            dest.colored = True

        self.g.filtered_all_pairs_shortest_path(
            vertex_filter=host_filter, path_action=path_action, num_workers=32
        )

    def restore_deleted_edges(self):
        """
        Restores deleted edges.
        This method reverses the "deletion" process for the edges within FIREWHEEL.
        Currently, that process (:py:meth:`firewheel.control.experiment_graph.Edge.delete`)
        simply marks the edge as invalid and removes the edge from the graph. This method
        is the reverse of that operation. We do this to keep the same graph IDs and original
        objects.
        """
        self.log.debug("Restoring %d deleted edges.", len(self.to_delete))
        for edge in self.to_delete:
            # Until there is an `undelete` method for an edge, this will sufficiently
            # reverse the process while keeping the original graph IDs.
            edge.source.g._add_edge(edge.source.graph_id, edge.destination.graph_id)
            edge.source.g.g.adj[edge.source.graph_id][edge.destination.graph_id][
                "object"
            ] = edge
            edge.valid = True

    def prune_non_colored_nodes(self):
        """
        Removes non-colored routers and switches.
        """
        self.log.debug("\t=> deleting from graph")

        rtr_delete_list = []
        for rtr in filter(
            lambda vertex: vertex.is_decorated_by(GenericRouter), self.g.get_vertices()
        ):
            try:
                if rtr.colored is not True:
                    rtr_delete_list.append(rtr)
            except AttributeError:
                rtr_delete_list.append(rtr)
        self.log.info("\t=> deleting %d routers from graph", len(rtr_delete_list))
        self.deleted_routers = set()
        for rtr in rtr_delete_list:
            router_as = rtr.routing["bgp"]["parameters"]["router-as"]
            if router_as:
                self.deleted_routers.add(router_as)
            rtr.delete()

        # Prune switches.
        switch_delete_list = []
        for switch in filter(
            lambda vertex: vertex.is_decorated_by(Switch), self.g.get_vertices()
        ):
            # Then, prune off the disconnected switches
            if switch.get_degree() == 0:
                switch_delete_list.append(switch)
                continue
            # Additionally, nix all switches that aren't colored but are connected
            try:
                if switch.colored is not True and switch.name.startswith("BGP-"):
                    switch_delete_list.append(switch)
            except AttributeError:
                if switch.name.startswith("BGP-"):
                    switch_delete_list.append(switch)
        self.log.info("\t=> deleting %d switches from graph", len(switch_delete_list))
        for switch in switch_delete_list:
            switch.delete()

    def clean_up_interfaces_and_bgp_neighbors(self):
        """
        Cleans up interfaces, BGP neighbors, and advertised networks.
        """
        self.log.info(
            "\t=> cleaning up interfaces, BGP neighbors, and advertised networks"
        )
        for as_vtx in filter(
            lambda vertex: vertex.is_decorated_by(GenericRouter), self.g.get_vertices()
        ):
            self.log.info("We are on Vertex %s", as_vtx.name)
            # Clean up interfaces to only connected switches
            neighbors = as_vtx.get_neighbors()
            good_switches = []
            good_nets = []
            for neighbor in neighbors:
                if not neighbor.is_decorated_by(Switch):
                    continue
                if (
                    not neighbor.name.startswith("BGP-")
                    and not neighbor.name == "SWITCH_BGP_CONTROL"
                ):
                    continue
                good_switches.append(neighbor.name)
                assert isinstance(neighbor.network, netaddr.IPNetwork)
                good_nets.append(neighbor.network)

            ifs = as_vtx.interfaces.interfaces
            if not ifs:
                continue

            # Need to cull the number of interfaces that are on the BGP control switch.
            # We don't need them all and it makes booting the topology difficult

            # Copy over only good ifs, changing ethX as appropriate
            del_list = []
            for iface in ifs:
                try:
                    if iface["switch"].name not in good_switches:
                        # Do not copy it over
                        del_list.append(iface)
                except KeyError:
                    pass
            for iface in del_list:
                as_vtx.interfaces.del_interface(iface["name"])

            if del_list:
                as_vtx.interfaces.rekey_interfaces()

            # Similarly, kill all BGP networks no longer connected
            try:
                bgp_nets = as_vtx.routing["bgp"]["networks"]

                if bgp_nets:
                    for bgp in list(bgp_nets):
                        assert isinstance(bgp, netaddr.IPNetwork)
                        if bgp not in good_nets:
                            bgp_nets.remove(bgp)
            except KeyError:
                # Key errors aren't a problem, just means bgp_nets don't exist
                pass

            # Next, clear any BGP neighbors that aren't connected
            try:
                bgps = as_vtx.routing["bgp"]["neighbors"]

                if bgps:
                    for bgp in list(bgps):
                        # remote_as = bgp['remote-as']
                        if bgp["remote-as"] in self.deleted_routers:
                            bgps.remove(bgp)

                        # Also, remove self links
                        if (
                            bgp["remote-as"]
                            == as_vtx.routing["bgp"]["parameters"]["router-as"]
                        ):
                            bgps.remove(bgp)
            except KeyError:
                # Similar to above, just means no neighbors
                pass

    def remove_unused_bgp_interfaces(self):
        """
        Collects next hop IP addresses and removes unused BGP interfaces.
        Those interfaces would never be used and it's best to boot a VM with
        the least number of interfaces as possible for performance reasons.
        """
        next_hops = set()
        for router in filter(
            lambda vertex: vertex.is_decorated_by(GenericRouter), self.g.get_vertices()
        ):
            try:
                bgp_neighbors = router.routing["bgp"]["neighbors"]
            except KeyError:
                continue
            for neighbor in bgp_neighbors:
                next_hops.add(str(neighbor["address"]))

        for router in filter(
            lambda vertex: vertex.is_decorated_by(GenericRouter), self.g.get_vertices()
        ):
            del_interfaces = []
            for interface in router.interfaces.interfaces:
                if (
                    interface["switch"].name == "SWITCH_BGP_CONTROL"
                    and str(interface["address"]) not in next_hops
                ):
                    del_interfaces.append(interface)

            for interface in del_interfaces:
                router.interfaces.del_interface(interface["name"])
