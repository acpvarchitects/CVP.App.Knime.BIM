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

@knext.node(name="IFC Reader", node_type=knext.NodeType.SOURCE, icon_path="icons/ifc.png", category=ifc_category)
@knext.input_table(name="Model List", description="List of IFC Models")
@knext.output_table(name="Output Data", description="Whatever the node has produced")


class IFCReader:
    """

    This node reads IFC Files within a specific folder (or a list of folders) and output a dataframe one line for each IFC Object and con columns properties

    """

    #model_param = knext.StringParameter("Model Path", "The classic placeholder", "foobar")
    models_column = knext.ColumnParameter("Model List Column","Paths of IFC Models",port_index=0)

    def ifcopenshellreader(self, path):
        model = ifcopenshell.open(path)

        dict = {}
        # All objects need to have an IfcBuildingStorey
        
        for storey in model.by_type("IfcBuildingStorey"):
            elements = element.get_decomposition(storey)

            for elem in elements:
                pset= element.get_psets(elem)
                subDict = {}
                ifcType = elem.is_a()
                subDict["ifcType"] = ifcType   
                classificationReference = list(classification.get_references(elem))
                for cl in classificationReference:   
                    className = cl.ReferencedSource.Name + "_" +cl.ItemReference[:2]
                    subDict[className + ": ItemReference"] = cl.ItemReference
                    subDict[className + ": Name"] = cl.Name 
                if elem.Name:
                    elementIdentity = elem.Name.split(':')
                    if len(elementIdentity)>1:
                        subDict['ElementName'] = elementIdentity[1]
                if pset:             
                    for ps in pset.values():
                        subDict.update(ps)                   
                subDict['ExtendedElementName'] = elementIdentity
                associations = elem.HasAssociations
                materialNumber = 0
                thkNumber = 0
                usedMaterials = []
                for i in associations:
                    try:
                        if i.RelatingMaterial.is_a('IfcMaterial'):
                            if i.RelatingMaterial.Name not in usedMaterials:   
                                usedMaterials.append(i.RelatingMaterial.Name)
                                materialNumber += 1
                                subDict["Material_" + str(materialNumber).zfill(3)] = i.RelatingMaterial.Name
                        if i.RelatingMaterial.is_a('IfcMaterialList'):
                            for material in i.RelatingMaterial.Materials:
                                if material.Name not in usedMaterials:
                                    usedMaterials.append(material.Name)
                                    materialNumber += 1
                                    subDict["Material_" + str(materialNumber).zfill(3)] = material.Name
                        if i.RelatingMaterial.is_a('IfcMaterialLayerSetUsage'):
                            mLayers = list(i.RelatingMaterial.ForLayerSet.MaterialLayers)
                            for m in mLayers:
                                materialNumber += 1
                                subDict["Material_" + str(materialNumber).zfill(3)] = m.Material.Name
                                thkNumber += 1
                                subDict["LayerThk_" + str(materialNumber).zfill(3)] = m.LayerThickness
                    except:
                        pass
                locMatrix = placement.get_local_placement(elem.ObjectPlacement)
                x,y,z = locMatrix[0][-1], locMatrix[1][-1], locMatrix[2][-1]
                subDict["Global X"], subDict["Global Y"], subDict["Global Z"] = x,y,z
                #subDict['LocationMatrix'] = locMatrix
                dict[elem.GlobalId] = subDict

        df = pd.DataFrame(dict)
        df = df.transpose()
        df['ModelPath'] = path
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
