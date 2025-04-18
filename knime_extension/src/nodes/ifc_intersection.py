import knime_extension as knext
import ifcopenshell
import ifcopenshell.geom
import ifcopenshell.util.shape
import multiprocessing
import pandas as pd
from .categories import category

# Node development reference links:
# https://www.knime.com/blog/4-steps-for-your-python-team-to-develop-knime-nodes
# https://www.knime.com/blog/python-script-node-bundled-packages
# https://docs.knime.com/latest/pure_python_node_extensions_guide/index.html#_defining_custom_port_objects

# IFC Intersection Node

@knext.node(
    name="IFC Intersection",
    node_type=knext.NodeType.SOURCE,
    icon_path="icons/ifc.png",
    category=category,
    after="",
    )
@knext.input_table(name="Rooms IFC File", description="Table containing paths to the IFC file with rooms")
@knext.input_table(name="Elements IFC File", description="Table containing paths to the IFC file with elements")
@knext.output_table(name="Elements with Room Mapping", description="Table containing elements and their respective rooms")

class IFCRoomMapping:
    """
    This node processes two IFC files (one containing rooms and another containing elements) and determines which objects belong to which room.
    """
    rooms_column = knext.ColumnParameter("Rooms IFC File Column", "Column containing the path to the IFC file with rooms", port_index=0)
    elements_column = knext.ColumnParameter("Elements IFC File Column", "Column containing the path to the IFC file with elements", port_index=1)

    def map_elements_to_rooms(self, rooms_ifc_path, elements_ifc_path):
        ifc_rooms = ifcopenshell.open(rooms_ifc_path)
        ifc_elements = ifcopenshell.open(elements_ifc_path)

        element_centroids = {}
        settings = ifcopenshell.geom.settings()
        iterator = ifcopenshell.geom.iterator(settings, ifc_elements, multiprocessing.cpu_count())

        if iterator.initialize():
            while True:
                shape = iterator.get()
                element = ifc_elements.by_id(shape.id)
                guid = element.GlobalId
                centroid = ifcopenshell.util.shape.get_shape_bbox_centroid(shape, shape.geometry)
                element_centroids[shape.id] = centroid
                if not iterator.next():
                    break

        tree = ifcopenshell.geom.tree()
        iterator = ifcopenshell.geom.iterator(settings, ifc_rooms, multiprocessing.cpu_count())

        if iterator.initialize():
            while True:
                native_shape = iterator.get_native()
                if native_shape:
                    tree.add_element(native_shape)
                if not iterator.next():
                    break

        step_id_to_guid = {step_id: ifc_elements.by_id(step_id).GlobalId for step_id in element_centroids}

        mapped_elements = []
        for step_id, centroid in element_centroids.items():
            element_guid = step_id_to_guid.get(step_id, "UNKNOWN_GUID")
            matching_room = tree.select(centroid.tolist(), completely_whitin=True)
            room_id = matching_room[0] if matching_room else ""
            mapped_elements.append({
                "ElementGUID": str(element_guid),
                "IsContained": str(room_id)
            })

        elements_df = pd.DataFrame(mapped_elements).astype(str)
        return elements_df

    def configure(self, configure_context, input_schema_1, input_schema_2):
        if len(input_schema_1.column_names) == 0 or len(input_schema_2.column_names) == 0:
            raise ValueError("One or both input tables have no columns. Ensure they contain at least one column in KNIME.")

    def execute(self, exec_context, input_1, input_2):
        df_rooms = input_1.to_pandas()
        df_elements = input_2.to_pandas()

        if df_rooms.empty or df_elements.empty:
            raise ValueError("One of the input tables is empty. Ensure valid IFC file paths are provided.")

        rooms_path = df_rooms[self.rooms_column].iloc[0]
        elements_path = df_elements[self.elements_column].iloc[0]

        elements_df = self.map_elements_to_rooms(rooms_path, elements_path)

        return knext.Table.from_pandas(elements_df) 
