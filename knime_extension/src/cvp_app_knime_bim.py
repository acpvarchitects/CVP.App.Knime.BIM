# The root category of all IFC categories
import knime_extension as knext
import sys

import os

# This defines the root Geospatial KNIME category that is displayed in the node repository
category = knext.category(
    path="/community",
    level_id="bim",
    name="BIM",
    description="Nodes for Building Information Modelling",
    # starting at the root folder of the extension_module parameter in the knime.yml file
    icon="icons/bim.png",
)

# The different node files
import nodes.cvp_app_knime_ifc