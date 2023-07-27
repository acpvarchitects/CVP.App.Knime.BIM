import logging
import knime.extension as knext

import ifcopenshell
from ifcopenshell.util import element, classification, placement
import pandas as pd
LOGGER = logging.getLogger(__name__)

# https://www.knime.com/blog/4-steps-for-your-python-team-to-develop-knime-nodes
# https://www.knime.com/blog/python-script-node-bundled-packages
# https://docs.knime.com/latest/pure_python_node_extensions_guide/index.html#_defining_custom_port_objects

# define the category and its subcategories
main_category = knext.category(
    path="/community",
    level_id="bim",
    name="BIM",
    description="Nodes for Building Information Modelling",
    icon="icons/bim.png",
)

ifc_category = knext.category(
    path=main_category,
    level_id="ifc",
    name="IFC",
    description="Nodes for IFC Manipulation",
    icon="icons/ifc.png",
)

@knext.node(name="IFC Building", node_type=knext.NodeType.SOURCE, icon_path="icons/ifc.png", category=ifc_category)
@knext.input_table(name="Model List", description="List of IFC Models")
@knext.output_table(name="Output Data", description="Whatever the node has produced")


class IFCBuilding:
    """

    This node reads IFC Building Info within a specific folder (or a list of folders) and output a dataframe one line for the IfcBuilding properties

    """

    #model_param = knext.StringParameter("Model Path", "The classic placeholder", "foobar")
    models_column = knext.ColumnParameter("Model List Column","Paths of IFC Models",port_index=0)

    def ifcopenshellreader(self, path):
        model = ifcopenshell.open(path)

        building = model.by_type('IfcBuilding')
        buildPset=element.get_psets(building[0])
        dict={}
        if buildPset:             
            for ps in buildPset.values():
                dict.update(ps)   
        df = pd.DataFrame({building[0].GlobalId: dict})  
        df = df.transpose()
        df
        return df

    def configure(self, configure_context, input_schema_1):
        return input_schema_1

    def execute(self, exec_context, input_1):

        df_models_list = input_1.to_pandas()

        df_list = []

        for model in df_models_list['Path']:
            df_list.append(self.ifcopenshellreader(model))

        df_full = pd.concat(df_list, ignore_index=False)
        
        #df_full = df_full.convert_dtypes()
        df_full = df_full.astype('string')

        #https://github.com/mdjska/daylight-analysis/blob/main/daylight_analysis_load_IFC_data.py
        #https://community.osarch.org/discussion/510/ifcopenshell-get-wall-layers-and-materials

        return knext.Table.from_pandas(df_full)
