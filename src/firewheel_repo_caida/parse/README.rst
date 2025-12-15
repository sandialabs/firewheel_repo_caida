.. _caida.parse_mc:

###########
caida.parse
###########

This FIREWHEEL model component is designed to import and process Center for Applied Internet Data Analysis (CAIDA) `Autonomous System (AS) <https://en.wikipedia.org/wiki/Autonomous_system_(Internet)>`_ trace data into a FIREWHEEL graph.
The plugin reads AS links and "prefix-to-AS" mappings, generates AS links, assigns BGP networks, and removes OSPF information.

**Attribute Provides:**
    * ``internet_ases``
    * ``internet_as_annotation``


**Attribute Depends:**
    * ``graph``


**Model Component Dependencies:**
    * :ref:`base_objects_mc`
    * :ref:`generic_vm_objects_mc`


*********************
Getting Required Data
*********************

The data used is from two CAIDA datasets:

1. **ARK IPv4 AS Links** - We combine data from all three teams.
   - URL: https://publicdata.caida.org/datasets/topology/ark/ipv4/as-links/

2. **Routeviews Prefix-to-AS Mappings for IPv4 and IPv6**
   - URL: https://publicdata.caida.org/datasets/routing/routeviews-prefix2as/

We typically use a one-month sample from each dataset, then process the data into a single file.
This process is currently automated, to use data from August 2018.
To replicate this process, with a different set of data, please review the ``INSTALL`` file.

***************
Seg Fault Issue
***************

This model component was previously built using `pysubnettree <https://pypi.org/project/pysubnettree/>`__, but the package occasionally caused seg faults.
If pytricia is ever deprecated, moving back to `pysubnettree <https://pypi.org/project/pysubnettree/>`__ could be a potential option.
If the model component silently fails, adding the following lines to the top of ``plugin.py`` could help debug:

.. code-block:: python

    import faulthandler
    faulthandler.enable()


******
Plugin
******

.. automodule:: caida.parse_plugin
    :members:
    :undoc-members:
    :special-members:
    :private-members:
    :show-inheritance:
    :exclude-members: __dict__,__weakref__,__module__


*****************
Available Objects
*****************

.. automodule:: caida.parse
    :members:
    :undoc-members:
    :special-members:
    :private-members:
    :show-inheritance:
    :exclude-members: __dict__,__weakref__,__module__
