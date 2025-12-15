import pytricia


class ASAnnotation(object):
    """
    The ASAnnotation class is used to manage and annotate Autonomous System (AS)
    subnets within a network graph. It leverages the pytricia library to store and
    retrieve subnet information efficiently.
    """

    def __init__(self, name):
        """
        Initializes the ASAnnotation instance.

        Args:
            name (str): The name of the annotation.
        """
        self.tree = pytricia.PyTricia()
        self.type = "annotation"
        self.name = name

    def add_subnet(self, new_subnet, as_name, switch):
        """
        Adds a new subnet to the annotation tree.

        Args:
            new_subnet (netaddr.IPNetwork): The subnet to be added.
            as_name (str): The name of the Autonomous System (AS) associated with the subnet.
            switch (base_objects.Switch): The Switch associated with the subnet.
        """
        self.tree[str(new_subnet)] = (as_name, switch)

    def get_as_for_subnet(self, subnet):
        """
        Retrieves the AS name for a given subnet.

        Args:
            subnet (netaddr.IPNetwork): The subnet for which to retrieve the AS name.

        Returns:
            str: The AS name associated with the subnet.
        """
        return self.tree[str(subnet)][0]

    def get_switch_for_subnet(self, subnet):
        """
        Retrieves the switch for a given subnet.

        Args:
            subnet (netaddr.IPNetwork): The subnet for which to retrieve the switch.

        Returns:
            base_objects.Switch: The Switch associated with the subnet.
        """
        return self.tree[str(subnet)][1]

    def is_network_in_tree(self, subnet):
        """
        Checks if a given subnet is present in the annotation tree.

        Args:
            subnet (netaddr.IPNetwork): The subnet to check.

        Returns:
            bool: :py:data:`True` if the subnet is present in the tree, :py:data:`False` otherwise.
        """
        return str(subnet) in self.tree
