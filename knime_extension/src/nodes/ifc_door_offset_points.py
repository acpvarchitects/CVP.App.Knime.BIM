import knime_extension as knext
import ifcopenshell
import ifcopenshell.util.placement
import pandas as pd
import numpy as np
from .categories import category

# Node development reference links:
# https://www.knime.com/blog/4-steps-for-your-python-team-to-develop-knime-nodes
# https://www.knime.com/blog/python-script-node-bundled-packages
# https://docs.knime.com/latest/pure_python_node_extensions_guide/index.html#_defining_custom_port_objects


# IFC Door Offset Points Node

@knext.node(
    name="IFC Door Offset XYZ",
    node_type=knext.NodeType.SOURCE,
    icon_path="icons/ifc.png",
    category=category,
    after="",
)
@knext.input_table(name="IFC Path Table", description="Table containing IFC model paths")
@knext.output_table(name="Door Offset Points", description="Offset points for IfcDoor elements")


class IFCDoorOffsetPointsExtractor:
    path_column = knext.ColumnParameter(
        "IFC Path Column",
        "Column containing the path to the IFC file",
        port_index=0,
    )

    def configure(self, configure_context, input_schema):
        return None

    def execute(self, exec_context, input_table):
        df = input_table.to_pandas()

        if df.empty:
            raise ValueError("The input table is empty.")
        if self.path_column not in df.columns:
            raise ValueError(f"The specified column '{self.path_column}' is not present in the input table.")

        ifc_path = df[self.path_column].iloc[0]
        model = ifcopenshell.open(ifc_path)
        doors = model.by_type("IfcDoor")

        offset_distance = 1500.0  # Already in millimeters
        data = []

        for door in doors:
            try:
                placement = door.ObjectPlacement
                matrix = ifcopenshell.util.placement.get_local_placement(placement)

                if not door.Representation:
                    continue

                direction_y = matrix[:3, 1]
                norm_y = direction_y / np.linalg.norm(direction_y)

                for rep in door.Representation.Representations:
                    if rep.RepresentationType == "BoundingBox":
                        for item in rep.Items:
                            if item.is_a("IfcBoundingBox"):
                                corner = np.array(item.Corner.Coordinates, dtype=float)
                                x_dim, y_dim, z_dim = float(item.XDim), float(item.YDim), float(item.ZDim)
                                center_local = corner + np.array([x_dim, y_dim, z_dim], dtype=float) / 2.0
                                center_global = matrix[:3, :3] @ center_local + matrix[:3, 3]

                                # No conversion necessary: all values are in millimeters
                                offset_pos = center_global + offset_distance * norm_y
                                offset_neg = center_global - offset_distance * norm_y

                                for pt, label in zip([offset_pos, offset_neg], ["Offset_Pos", "Offset_Neg"]):
                                    data.append([
                                        float(pt[0]),
                                        float(pt[1]),
                                        float(pt[2]),
                                        door.GlobalId,
                                        label
                                    ])

            except Exception as e:
                print(f"Error processing door {door.GlobalId}: {e}")
                continue

        result_df = pd.DataFrame(data, columns=["X", "Y", "Z", "GlobalID", "PointType"])

        # Optional: keep float precision for KNIME output
        pd.options.display.float_format = '{:.8f}'.format

        return knext.Table.from_pandas(result_df)