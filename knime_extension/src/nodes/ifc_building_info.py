import knime_extension as knext
import ifcopenshell
from ifcopenshell.util import element
import pandas as pd
from .categories import category


# IFC Building Info Reader Node

@knext.node(
    name="IFC Building Info",
    node_type=knext.NodeType.SOURCE,
    icon_path="icons/ifc.png",
    category=category,
    after="",
    )
@knext.input_table(name="Model List", description="List of IFC Models")
@knext.output_table(name="Output Data", description="Whatever the node has produced")

class IFCBuilding:
    """

    This node reads IFC Building Info within a specific folder (or a list of folders) and output a dataframe one line for the IfcBuilding properties

    """

    #model_param = knext.stringParameter("Model Path", "The classic placeholder", "foobar")
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
        return df

    def configure(self, configure_context, input_schema_1):
        return input_schema_1

    def execute(self, exec_context, input_1):

        df_models_list = input_1.to_pandas()

        df_list = []

        for model in df_models_list['Path']:
            df_list.append(self.ifcopenshellreader(model))

        df_full = pd.concat(df_list, ignore_index=True)
        
        #df_full = df_full.convert_dtypes()
        df_full = df_full.astype('string')

        #https://github.com/mdjska/daylight-analysis/blob/main/daylight_analysis_load_IFC_data.py
        #https://community.osarch.org/discussion/510/ifcopenshell-get-wall-layers-and-materials

        return knext.Table.from_pandas(df_full)
    
