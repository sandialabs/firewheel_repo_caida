.. _caida.prune_routers_mc:

###################
caida.prune_routers
###################

This model component removes routers not involved in any shortest path within the network topology.
It utilizes `NetworkX <https://networkx.org>`__ to compute shortest paths, prunes non-essential routers and switches, and cleans up interfaces, BGP neighbors, and advertised networks.
This ensures the network topology is optimized and contains only necessary components.


**Attribute Provides:**
    * ``pruned_internet_ases``

**Attribute Depends:**
    * ``graph``

**Model Component Dependencies:**
    * :ref:`generic_vm_objects_mc`

******
Plugin
******

.. automodule:: caida.prune_routers_plugin
    :members:
    :undoc-members:
    :special-members:
    :private-members:
    :show-inheritance:
    :exclude-members: __dict__,__weakref__,__module__
