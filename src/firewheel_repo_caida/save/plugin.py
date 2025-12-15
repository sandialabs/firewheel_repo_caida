import json
from pprint import pprint

from base_objects import VMEndpoint

from firewheel.control.experiment_graph import AbstractPlugin


class Save(AbstractPlugin):
    """
    Save the current experiment network topology to a JSON file.
    """

    def run(self, filename):
        """
        Save the current experiment network topology to a JSON file.
        Switches are not included in the output as they can be inferred from
        :py:class:`base_objects.VMEndpoint` interfaces.

        Args:
            filename (str): The path to the JSON file where the topology data will be saved.

        Raises:
            TypeError: If the filename is not provided.
        """
        if not filename:
            raise TypeError(
                "Must provide a filename to ``caida.save`` for the JSON output."
            )

        output = {"vertices": []}

        for vertex in self.g.get_vertices():
            if not vertex.is_decorated_by(VMEndpoint):
                # Don't need switches since they can be backed out from
                # VMEndpoint interfaces
                continue

            attributes = {}

            for obj in vertex.__dict__:
                if obj in {"valid", "skip_list", "graph_id"}:
                    continue
                if self.is_jsonable(vertex.__dict__[obj]):
                    attributes[obj] = vertex.__dict__[obj]

            try:
                attributes["interfaces"] = []
                for interface in vertex.interfaces.interfaces:
                    iface = {}
                    for key in interface:
                        if key == "switch":
                            iface[key] = interface[key].name
                        else:
                            iface[key] = str(interface[key])
                    attributes["interfaces"].append(iface)
            except KeyError:
                pass

            try:
                # Trigger KeyError to skip if this vertex
                # isn't configured for BGP routing
                vertex.routing["bgp"]

                # Pick up the routing dictionary that was
                # skipped above due to unserializable values
                attributes["routing"] = vertex.routing

                try:
                    networks = []
                    for network in attributes["routing"]["bgp"]["networks"]:
                        networks.append(str(network))
                    attributes["routing"]["bgp"]["networks"] = networks
                except KeyError:
                    # Not every BGP router advertises its own networks
                    pass

                try:
                    neighbors = {}
                    for n in attributes["routing"]["bgp"]["neighbors"]:
                        neighbor = self.find_router_by_as(n["remote-as"])
                        if not neighbor:
                            print(
                                "Could not find neighbor with AS: %s" % n["remote-as"]
                            )
                            continue
                        switch = self.find_switch(vertex, neighbor)
                        if not switch:
                            print(
                                "Could not find switch between: %s <-> %s"
                                % (vertex.name, neighbor.name)
                            )
                            continue
                        neighbors[neighbor.name] = switch

                    attributes["routing"]["bgp"]["neighbors"] = neighbors
                except KeyError:
                    print("BGP router has no neighbors: %s" % vertex.name)

            except AttributeError:
                # This is an out if this vertex isn't a router and therefore
                # does not have a routing attribute
                pass
            except KeyError:
                # This is an out for routers that don't have BGP configured
                pass
            except Exception:  # noqa: BLE001
                print("Could not handle routing parameters:")
                pprint(vertex.routing)
                del attributes["routing"]

            output["vertices"].append(attributes)

        with open(filename, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=4)

    def is_jsonable(self, obj):
        """
        Check if an object can be serialized to JSON.

        Args:
            obj (Vertex): The object to check.

        Returns:
            bool: :py:data:`True` if the object can be serialized to JSON, :py:data:`False` otherwise.
        """
        try:
            json.dumps(obj)
            return True
        except TypeError:
            return False

    def find_router_by_as(self, bgp_as):
        """
        Find a router vertex by its BGP AS number.

        Args:
            bgp_as (int): The BGP AS number to search for.

        Returns:
            Vertex: The router vertex with the specified BGP AS number, or None if not found.
        """
        for v in self.g.get_vertices():
            if v.type != "router":
                continue
            try:
                remote_as = v.routing["bgp"]["parameters"]["router-as"]
                if remote_as == bgp_as:
                    return v
            except AttributeError:
                # Handle routers with no routing information
                continue
            except KeyError:
                # Handle non-BGP routers
                continue
        return None

    def find_switch(self, v1, v2):
        """
        Find a switch vertex that connects two router vertices.
        If multiple switches are found, a warning is printed and only
        one the switches is returned.

        Args:
            v1 (Vertex): The first router vertex.
            v2 (Vertex): The second router vertex.

        Returns:
            Vertex: The switch vertex that connects the two routers, or None if not found.
        """
        v1_switches = set()
        for interface in v1.interfaces.interfaces:
            v1_switches.add(interface["switch"].name)
        v2_switches = set()
        for interface in v2.interfaces.interfaces:
            v2_switches.add(interface["switch"].name)

        result = v1_switches & v2_switches
        if not result:
            return None
        if len(result) > 1:
            print(
                "Found multiple switches between routers: %s <-> %s"
                % (v1.name, v2.name)
            )

        # only return a single switch
        return result.pop()
