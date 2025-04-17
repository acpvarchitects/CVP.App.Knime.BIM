import knime_extension as knext

# define the category and its subcategories
category = knext.category(
    path="/community/bim",
    level_id="ifc",
    name="IFC",
    description="Nodes for IFC Manipulation",
    # starting at the root folder of the extension_module parameter in the knime.yml file
    icon="icons/ifc.png",
)