from random import choice

from netaddr import IPNetwork
from base_objects import VMEndpoint
from generic_vm_objects import GenericRouter

from firewheel.control.experiment_graph import Vertex, AbstractPlugin


class Topology(AbstractPlugin):
    """
    This plugin creates a test CAIDA topology by connecting a specified number of hosts
    to BGP networks. It selects a given number of routers with BGP networks, creates hosts,
    and connects them to the appropriate switches.
    """

    def run(self, num_hosts="10"):
        """
        Executes the topology creation process.

        The method performs the following steps:
        1. Converts the num_hosts parameter to an integer.
        2. Selects routers with BGP networks.
        3. Chooses a specified number of routers randomly.
        4. Creates hosts and connects them to the appropriate switches.

        Args:
            num_hosts (str): The number of hosts to create.
                This should be convertible to an Integer. Defaults to "10".

        Raises:
            ValueError: If the provided ``num_hosts`` parameter is not an integer.
            RuntimeError: If no suitable nodes are found in the graph.
        """
        try:
            num_hosts = int(num_hosts)
        except ValueError:
            print("Must provide an integer as a parameter to the test CAIDA topology")
            raise

        chosen = []
        nodes = []
        for vertex in self.g.get_vertices():
            if vertex.is_decorated_by(GenericRouter) and vertex.get_all_bgp_networks():
                nodes.append(vertex)

        if not nodes:
            raise RuntimeError(f"No nodes found: {len(nodes)}")

        for _i in range(num_hosts):
            router = choice(nodes)
            chosen.append(router)
            nodes.remove(router)

        for router in chosen:
            networks = router.get_all_bgp_networks()
            network = IPNetwork(networks[0])

            switch = self.g.find_vertex(
                "BGP-%s" % str(network.cidr).replace(".", "-").replace("/", "-")
            )
            if not switch:
                print(
                    "Unable to find switch: %s"
                    % "BGP-%s"
                    % str(network.cidr).replace(".", "-").replace("/", "-")
                )
                continue

            host = Vertex(self.g, router.name.replace("router", "host"))
            host.decorate(VMEndpoint)

            host.connect(switch, network[2], str(network.netmask))
