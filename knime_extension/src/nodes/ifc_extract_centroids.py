import knime_extension as knext
import ifcopenshell
from ifcopenshell.util import element
import ifcopenshell.util.shape
import ifcopenshell.geom
import multiprocessing
import pandas as pd
from .categories import category

# https://www.knime.com/blog/4-steps-for-your-python-team-to-develop-knime-nodes
# https://www.knime.com/blog/python-script-node-bundled-packages
# https://docs.knime.com/latest/pure_python_node_extensions_guide/index.html#_defining_custom_port_objects

#IFC Extract Element Centroids

@knext.node(
    name="IFC Extract Element Centroids",
    node_type=knext.NodeType.SOURCE,
    icon_path="icons/ifc.png",
    category=category,
    after="",
)
@knext.input_table(name="IFC Path Table", description="Table containing IFC model paths")
@knext.output_table(name="Centroid Data", description="Centroids with metadata for each IFC element")


class IFCCentroidExtractor:
    """
    This node reads an IFC file and computes the 3D bounding box centroid for each element.
    The output table contains coordinates (in millimeters), the element GlobalId, the building storey name,
    and the custom property 'CVP_Tag Code' from the PSet 'CVP_Code' if available.
    """

    path_column = knext.ColumnParameter(
        "IFC Path Column",
        "Column containing the path to the IFC file",
        port_index=0,
    )

    def get_storey_name(self, element, model):
        """
        Retrieve the name of the IfcBuildingStorey to which the element belongs.
        """
        for rel in model.by_type("IfcRelContainedInSpatialStructure"):
            if element in rel.RelatedElements:
                storey = rel.RelatingStructure
                if storey.is_a("IfcBuildingStorey"):
                    return storey.Name
        return "Unknown"

    def configure(self, configure_context, input_schema_1):
        return None

    def execute(self, exec_context, input_1):
        df = input_1.to_pandas()

        if df.empty:
            raise ValueError("The input table is empty.")
        if self.path_column not in df.columns:
            raise ValueError(f"The specified column '{self.path_column}' is not present in the input table.")

        ifc_path = df[self.path_column].iloc[0]
        print(f"[INFO] Opening IFC file: {ifc_path}")
        model = ifcopenshell.open(ifc_path)

        settings = ifcopenshell.geom.settings()
        settings.set(settings.USE_WORLD_COORDS, True)

        iterator = ifcopenshell.geom.iterator(settings, model, multiprocessing.cpu_count())
        if not iterator.initialize():
            raise RuntimeError("Unable to initialize the geometry iterator.")

        print("[INFO] Geometry iterator initialized. Starting extraction of centroids...")

        data = []
        processed = 0
        failed = 0

        while True:
            shape = iterator.get()
            if not shape:
                break

            element = model.by_id(shape.id)
            global_id = element.GlobalId if element else "N/A"
            level = self.get_storey_name(element, model) if element else "Unknown"

            id_item = "N/A"
            try:
                psets = ifcopenshell.util.element.get_psets(element)
                cvp = psets.get("CVP_Code", {})
                id_item = cvp.get("CVP_Tag Code", "N/A")
            except Exception as e:
                print(f"[WARN] Failed to retrieve CVP_Tag Code for {global_id}: {e}")

            try:
                centroid = ifcopenshell.util.shape.get_bbox_centroid(shape.geometry)
                centroid_mm = [coord * 1000 for coord in centroid]
                data.append([*centroid_mm, global_id, level, id_item])
                print(f"[OK] Found centroid for: {global_id}")
                processed += 1
            except Exception as e:
                print(f"[ERROR] Failed to get centroid for {global_id}: {e}")
                failed += 1

            if not iterator.next():
                break

        print(f"[DONE] Centroid extraction completed.")
        print(f"         Success: {processed}")
        print(f"         Failed : {failed}")
        print(f"         Total   : {processed + failed}")

        result_df = pd.DataFrame(data, columns=["X", "Y", "Z", "GlobalID", "Level", "ID_Item"])
        return knext.Table.from_pandas(result_df)