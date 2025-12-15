.. _caida.test_topology_mc:

###################
caida.test_topology
###################

This model component creates a test CAIDA topology by connecting a specified number of hosts
to BGP networks.
It depends on ``internet_ases`` being provided (typically by :ref:`caida.parse`).
Therefore, once the basic CAIDA topology has been created then a user given number of routers with BGP networks is selected, hosts are created, and then connected to these select networks via the appropriate switches.

This can be combined with :ref:`caida.prune_routers` to create an Internet-like infrastructure with a user-provided number of hosts connected to them.

.. code-block:: bash

    firewheel experiment caida.test_topology caida.prune_routers minimega.launch

An example output from this topology (using 2015 data) with default number of hosts (10) is shown below.

.. image:: https://raw.githubusercontent.com/sandialabs/firewheel_repo_caida/refs/heads/main/src/firewheel_repo_caida/tests/topology/caida_10_hosts_pruned.png
   :alt: An example of a pruned CAIDA topology with 10 hosts.
   :width: 600px
   :align: center
   :caption: This is an example of a pruned CAIDA topology with 10 hosts. The cyan nodes are routers, the yellow ones are FIREWHEEL Switches, and the magenta are host systems.

**Attribute Provides:**
    * ``topology``
    * ``caida_topology``

**Attribute Depends:**
    * ``internet_ases``

**Model Component Dependencies:**
    * :ref:`base_objects_mc`
    * :ref:`generic_vm_objects_mc`

******
Plugin
******

.. automodule:: caida.test_topology_plugin
    :members:
    :undoc-members:
    :special-members:
    :private-members:
    :show-inheritance:
    :exclude-members: __dict__,__weakref__,__module__
