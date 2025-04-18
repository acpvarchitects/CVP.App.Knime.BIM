import knime_extension as knext
import ifcopenshell
from ifcopenshell.util import element, classification, placement
import ifcopenshell.util.shape
import pandas as pd
from .categories import category

import logging
LOGGER = logging.getLogger(__name__)

# Node development reference links:
# https://www.knime.com/blog/4-steps-for-your-python-team-to-develop-knime-nodes
# https://www.knime.com/blog/python-script-node-bundled-packages
# https://docs.knime.com/latest/pure_python_node_extensions_guide/index.html#_defining_custom_port_objects


# IFC Reader Node

@knext.node(
    name="IFC Reader",
    node_type=knext.NodeType.SOURCE,
    icon_path="icons/ifc.png",
    category=category,
    after="",
    )
@knext.input_table(name="Model List", description="List of IFC Models")
@knext.output_table(name="Output Data", description="Whatever the node has produced")

class IFCReader:
    """
    KNIME node that reads IFC2x3 and IFC4 files (or later versions supported by IfcOpenShell),
    and returns a dataframe where each row represents an IFC element, with properties,
    classifications, materials, and placement data as columns.
    """

    def ifcopenshellreader(self, path: str) -> pd.DataFrame:
        """
        Opens an IFC file with IfcOpenShell and returns a dataframe
        containing all elements found in the model.
        Supports IFC2x3 and IFC4 formats.
        """
        model = ifcopenshell.open(path)
        dict_rows = {}

        # Get all building storeys (IfcBuildingStorey)
        storeys = model.by_type("IfcBuildingStorey")
        for storey in storeys:
            elements = element.get_decomposition(storey)

            for elem in elements:
                subDict = {}

                # 1) IFC type information
                ifcType = elem.is_a()
                subDict["ifcType"] = ifcType

                ifcElementType = element.get_type(elem)
                subDict["ifcElementType"] = ifcElementType

                # 2) Classifications (e.g. OmniClass, Uniclass, etc.)
                classificationReference = list(classification.get_references(elem))
                for cl in classificationReference:
                    try:
                        source_name = cl.ReferencedSource.Name if cl.ReferencedSource else "UnknownSource"
                        item_ref = cl.ItemReference if cl.ItemReference else "UnknownItem"
                        className = source_name + "_" + item_ref[:2]
                        subDict[className + ": ItemReference"] = item_ref
                        if cl.Name:
                            subDict[className + ": Name"] = cl.Name
                    except:
                        pass

                # 3) Element name (parsing colon-separated names if present)
                if elem.Name:
                    if ":" in elem.Name:
                        parts = elem.Name.split(":")
                        if len(parts) > 1:
                            subDict["ElementName"] = parts[1]
                    else:
                        subDict["ElementName"] = elem.Name

                # 4) Property Sets (Psets)
                pset = element.get_psets(elem)
                if pset:
                    for ps_values in pset.values():
                        if ps_values:
                            subDict.update(ps_values)

                # 5) Tag and Type Tag (if available)
                if hasattr(elem, "Tag") and elem.Tag:
                    subDict["Tag"] = elem.Tag
                if ifcElementType and hasattr(ifcElementType, "Tag") and ifcElementType.Tag:
                    subDict["ifcElementTypeTag"] = ifcElementType.Tag

                # 6) Materials (manual extraction approach)
                associations = getattr(elem, "HasAssociations", []) or []
                materialNumber = 0
                usedMaterials = []
                for assoc in associations:
                    mat = getattr(assoc, "RelatingMaterial", None)
                    if not mat:
                        continue

                    try:
                        if mat.is_a('IfcMaterial'):
                            mname = mat.Name
                            if mname not in usedMaterials:
                                usedMaterials.append(mname)
                                materialNumber += 1
                                subDict[f"Material_{str(materialNumber).zfill(3)}"] = mname

                        elif mat.is_a('IfcMaterialList'):
                            for m in mat.Materials:
                                if m.Name not in usedMaterials:
                                    usedMaterials.append(m.Name)
                                    materialNumber += 1
                                    subDict[f"Material_{str(materialNumber).zfill(3)}"] = m.Name

                        elif mat.is_a('IfcMaterialLayerSetUsage'):
                            layerSet = getattr(mat, "ForLayerSet", None)
                            if layerSet and hasattr(layerSet, "MaterialLayers"):
                                for lyr in layerSet.MaterialLayers:
                                    mname = lyr.Material.Name if lyr.Material else "UnnamedLayer"
                                    if mname not in usedMaterials:
                                        usedMaterials.append(mname)
                                        materialNumber += 1
                                        subDict[f"Material_{str(materialNumber).zfill(3)}"] = mname
                                    # Se vuoi anche salvare spessore
                                    subDict[f"LayerThk_{str(materialNumber).zfill(3)}"] = lyr.LayerThickness

                        elif mat.is_a('IfcMaterialConstituentSet'):
                            constituents = getattr(mat, "MaterialConstituents", [])
                            for c in constituents:
                                if c.Material and c.Material.Name not in usedMaterials:
                                    usedMaterials.append(c.Material.Name)
                                    materialNumber += 1
                                    subDict[f"Material_{str(materialNumber).zfill(3)}"] = c.Material.Name

                        elif mat.is_a('IfcMaterialProfileSetUsage'):
                            profSet = getattr(mat, "ForProfileSet", None)
                            if profSet and hasattr(profSet, "MaterialProfiles"):
                                for mp in profSet.MaterialProfiles:
                                    if mp.Material and mp.Material.Name not in usedMaterials:
                                        usedMaterials.append(mp.Material.Name)
                                        materialNumber += 1
                                        subDict[f"Material_{str(materialNumber).zfill(3)}"] = mp.Material.Name
                                    # Se vuoi recuperare spessori da mp.Profile, dipende dal tipo di profilo, ecc.
                    except:
                        pass

                # 6b) Optional: You could use IfcOpenShell utility functions instead (commented)
                # - element.get_material_layers(elem)
                # - element.get_material_profile_sets(elem)
                # - element.get_material_constituents(elem)

                # 7) Global coordinates (from ObjectPlacement)
                locMatrix = placement.get_local_placement(elem.ObjectPlacement)
                x, y, z = locMatrix[0][-1], locMatrix[1][-1], locMatrix[2][-1]
                subDict["Global X"], subDict["Global Y"], subDict["Global Z"] = x, y, z

                # 8) Clean up keys ending with whitespace
                wrongKeys = [key for key in subDict if key.endswith(' ')]
                for key in wrongKeys:
                    value = subDict.pop(key)
                    newKey = key.rstrip() + "(1)"
                    subDict[newKey] = value

                # 9) Store this element’s data using GlobalId
                dict_rows[elem.GlobalId] = subDict

        # Create dataframe and reset index
        df = pd.DataFrame(dict_rows).transpose().reset_index()
        df = df.rename(columns={'index': 'UniqueID'})

        # Add source model path
        df['ModelPath'] = path

        return df

    def configure(self, configure_context, input_schema_1):
        return None

    def execute(self, exec_context, input_1):
        """
        Executes the reading process on one or more IFC file paths
        and merges the results into a single dataframe.
        """
        df_models_list = input_1.to_pandas()

        df_list = []
        for model_path in df_models_list['Path']:
            df_list.append(self.ifcopenshellreader(model_path))

        df_full = pd.concat(df_list, ignore_index=True)

        # Convert all fields to string type (optional, for KNIME compatibility)
        df_full = df_full.astype('string')

        return knext.Table.from_pandas(df_full)


        #https://github.com/mdjska/daylight-analysis/blob/main/daylight_analysis_load_IFC_data.py
        #https://community.osarch.org/discussion/510/ifcopenshell-get-wall-layers-and-materials