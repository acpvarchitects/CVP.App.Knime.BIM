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
__category = knext.category(
    path="/community/bim",
    level_id="ifc",
    name="IFC",
    description="Nodes for IFC Manipulation",
    # starting at the root folder of the extension_module parameter in the knime.yml file
    icon="icons/ifc.png",
)


# IFC Reader Node

@knext.node(
    name="IFC Reader",
    node_type=knext.NodeType.SOURCE,
    icon_path="icons/ifc.png",
    category=__category,
    after="",
    )
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
                ifcElementType = ifcopenshell.util.element.get_type(elem)
                subDict["ifcElementType"] = ifcElementType  

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
                # Revit Element ID
                try:
                    subDict['Tag'] = elem.Tag
                except:
                    pass
                try:
                    subDict["ifcElementTypeTag"] = ifcElementType.Tag
                except:
                    pass
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

                # Detect and correct keys ending with space
                wrongKeys = [key for key in subDict if key.endswith(' ')] 
                for key in wrongKeys:
                    value = subDict.pop(key)
                    newKey = key.rstrip() + "(1)"
                    subDict[newKey] = value

                dict[elem.GlobalId] = subDict

        df = pd.DataFrame(dict)
        df = df.transpose()

        df = df.reset_index()
        df = df.rename(columns={'index': 'UniqueID'})
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

# IFC Building Info Reader Node

@knext.node(
    name="IFC Building Info",
    node_type=knext.NodeType.SOURCE,
    icon_path="icons/ifc.png",
    category=__category,
    after="",
    )
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

        df_full = pd.concat(df_list, ignore_index=True)
        
        #df_full = df_full.convert_dtypes()
        df_full = df_full.astype('string')

        #https://github.com/mdjska/daylight-analysis/blob/main/daylight_analysis_load_IFC_data.py
        #https://community.osarch.org/discussion/510/ifcopenshell-get-wall-layers-and-materials

        return knext.Table.from_pandas(df_full)