import knime_extension as knext
import ifcopenshell
from ifcopenshell.util import element, classification, placement
import ifcopenshell.util.shape
import pandas as pd
from .categories import category

import logging
LOGGER = logging.getLogger(__name__)

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
    Node KNIME che legge IFC 2x3 e IFC4 (e versioni successive supportate da IfcOpenShell),
    restituendo un dataframe con una riga per ciascun elemento IFC e con le proprietà
    (pset e materiali) come colonne.
    """

    # modello di base con KNIME:
    # models_column = knext.ColumnParameter("Model List Column", "Paths of IFC Models", port_index=0)

    def ifcopenshellreader(self, path: str) -> pd.DataFrame:
        """
        Legge un file IFC usando IfcOpenShell e restituisce un dataframe per tutti
        gli elementi trovati. Funziona con IFC2x3 e IFC4.
        """
        model = ifcopenshell.open(path)

        # Questo dict accumula i dati per ogni GlobalId
        dict_rows = {}

        # Recuperiamo tutte le storey (IfcBuildingStorey).
        # Puoi sostituire "model.by_type('IfcBuildingStorey')" con un altro criterio
        # se vuoi processare TUTTI gli elementi a prescindere dal BuildingStorey.
        storeys = model.by_type("IfcBuildingStorey")
        for storey in storeys:
            elements = element.get_decomposition(storey)

            for elem in elements:
                subDict = {}

                # 1) Tipi IFC base
                ifcType = elem.is_a()
                subDict["ifcType"] = ifcType

                # ifcElementType
                ifcElementType = element.get_type(elem)
                subDict["ifcElementType"] = ifcElementType

                # 2) Classificazioni
                classificationReference = list(classification.get_references(elem))
                for cl in classificationReference:
                    try:
                        # Verifica che ReferencedSource e ItemReference non siano None
                        source_name = cl.ReferencedSource.Name if cl.ReferencedSource else "UnknownSource"
                        item_ref = cl.ItemReference if cl.ItemReference else "UnknownItem"
                        # Uso i primi 2 caratteri come in IFC2x3, ma fai la logica che preferisci
                        className = source_name + "_" + item_ref[:2]
                        # Aggiungo i campi
                        subDict[className + ": ItemReference"] = item_ref
                        if cl.Name:
                            subDict[className + ": Name"] = cl.Name
                    except:
                        pass

                # 3) Nome dell'elemento (evita errori se non c'è ":" nel name)
                if elem.Name:
                    if ":" in elem.Name:
                        parts = elem.Name.split(":")
                        if len(parts) > 1:
                            subDict["ElementName"] = parts[1]
                    else:
                        # Se preferisci salvare comunque l'intero Name
                        subDict["ElementName"] = elem.Name

                # 4) Pset (Property Set)
                pset = element.get_psets(elem)
                if pset:
                    # pset è un dict con {nome_pset: {prop1: val1, prop2: val2...}, ...}
                    for ps_values in pset.values():
                        if ps_values:
                            subDict.update(ps_values)

                # 5) Tag e Tag del Type (quando presenti)
                if hasattr(elem, "Tag") and elem.Tag:
                    subDict["Tag"] = elem.Tag
                if ifcElementType and hasattr(ifcElementType, "Tag") and ifcElementType.Tag:
                    subDict["ifcElementTypeTag"] = ifcElementType.Tag

                # 6) Materiali - APPROCCIO MANUALE
                # ----------------------------------------------------------
                associations = getattr(elem, "HasAssociations", []) or []
                materialNumber = 0
                usedMaterials = []
                for assoc in associations:
                    mat = getattr(assoc, "RelatingMaterial", None)
                    if not mat:
                        continue

                    try:
                        # Caso IFC2x3 e IFC4 classico
                        if mat.is_a('IfcMaterial'):
                            mname = mat.Name
                            if mname not in usedMaterials:
                                usedMaterials.append(mname)
                                materialNumber += 1
                                subDict[f"Material_{str(materialNumber).zfill(3)}"] = mname

                        # IFC2x3: IfcMaterialList
                        elif mat.is_a('IfcMaterialList'):
                            for m in mat.Materials:
                                if m.Name not in usedMaterials:
                                    usedMaterials.append(m.Name)
                                    materialNumber += 1
                                    subDict[f"Material_{str(materialNumber).zfill(3)}"] = m.Name

                        # IFC2x3 & IFC4: IfcMaterialLayerSetUsage
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

                        # IFC4: IfcMaterialConstituentSet
                        elif mat.is_a('IfcMaterialConstituentSet'):
                            constituents = getattr(mat, "MaterialConstituents", [])
                            for c in constituents:
                                if c.Material and c.Material.Name not in usedMaterials:
                                    usedMaterials.append(c.Material.Name)
                                    materialNumber += 1
                                    subDict[f"Material_{str(materialNumber).zfill(3)}"] = c.Material.Name

                        # IFC4: IfcMaterialProfileSetUsage
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

                # 6.bis) Materiali - APPROCCIO CON LE UTILITY IFCOPEN SHELL
                # ----------------------------------------------------------
                # In alternativa, puoi usare queste funzioni di util.element:
                #
                # layers = element.get_material_layers(elem)  # per layer (IfcMaterialLayerSet)
                # profiles = element.get_material_profile_sets(elem)  # per profile sets
                # constituents = element.get_material_constituents(elem)  # per constituent sets
                #
                # E poi gestirne i valori. Ad esempio:
                #
                # if layers:
                #     for i, layer_info in enumerate(layers, start=1):
                #         subDict[f"Material_{str(i).zfill(3)}"] = layer_info["material"]  # if there's a 'material' key
                #         subDict[f"LayerThk_{str(i).zfill(3)}"] = layer_info.get("thickness", None)
                #
                # Se usi uno solo dei due approcci, commenta l'altro.

                # 7) Coordinate Globali (o locali)
                locMatrix = placement.get_local_placement(elem.ObjectPlacement)
                x, y, z = locMatrix[0][-1], locMatrix[1][-1], locMatrix[2][-1]
                subDict["Global X"], subDict["Global Y"], subDict["Global Z"] = x, y, z

                # 8) Correggi chiavi che finiscono con spazio
                wrongKeys = [key for key in subDict if key.endswith(' ')]
                for key in wrongKeys:
                    value = subDict.pop(key)
                    newKey = key.rstrip() + "(1)"
                    subDict[newKey] = value

                # 9) Memorizza subDict dentro il dict_rows
                dict_rows[elem.GlobalId] = subDict

        # Crea un DataFrame
        df = pd.DataFrame(dict_rows).transpose().reset_index()
        df = df.rename(columns={'index': 'UniqueID'})

        # Aggiungi la colonna ModelPath per tracciare da quale IFC arriva
        df['ModelPath'] = path

        return df

    def configure(self, configure_context, input_schema_1):
        return None

    def execute(self, exec_context, input_1):
        """
        Esegue la lettura di uno o più percorsi IFC (2x3 o 4) e concatena i risultati in un unico DataFrame.
        """
        # df_models_list = input_1.to_pandas()  # se stai usando KNIME con un dataframe d'ingresso
        # ipotizzo che la colonna si chiami 'Path' (adatta al tuo caso)
        df_models_list = input_1.to_pandas()

        df_list = []
        for model_path in df_models_list['Path']:
            df_list.append(self.ifcopenshellreader(model_path))

        df_full = pd.concat(df_list, ignore_index=True)

        # Se vuoi convertire i tipi a "string"
        df_full = df_full.astype('string')

        return knext.Table.from_pandas(df_full)


        #https://github.com/mdjska/daylight-analysis/blob/main/daylight_analysis_load_IFC_data.py
        #https://community.osarch.org/discussion/510/ifcopenshell-get-wall-layers-and-materials