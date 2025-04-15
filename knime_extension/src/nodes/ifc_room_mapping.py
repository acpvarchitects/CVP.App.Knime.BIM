import knime_extension as knext
import ifcopenshell
import ifcopenshell.geom
import ifcopenshell.util.shape
import multiprocessing
import pandas as pd
from .categories import category


# https://www.knime.com/blog/4-steps-for-your-python-team-to-develop-knime-nodes
# https://www.knime.com/blog/python-script-node-bundled-packages
# https://docs.knime.com/latest/pure_python_node_extensions_guide/index.html#_defining_custom_port_objects

# IFC Intersection Node

@knext.node(
    name="IFC intersection",
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
    Extracts interior points within each room in an IFC file using OpenCascade geometry,
    returning a 3D point cloud with room metadata.
    """

    path_column = knext.ColumnParameter(
        "IFC Path Column",
        "Column containing the path to the IFC file",
        port_index=0,
    )

    spacing = knext.DoubleParameter(
        "Grid Spacing [m]",
        "Spacing between points in the X/Y/Z grid",
        default_value=0.3,
    )

    min_offset_mm = knext.IntParameter(
        "Minimum Offset from Boundary [mm]",
        "Minimum distance from room surfaces to keep points (buffer zone)",
        default_value=100,
    )

    def get_storey_elevation(self, space, ifc_file):
        for rel in ifc_file.by_type("IfcRelAggregates"):
            if space in rel.RelatedObjects:
                storey = rel.RelatingObject
                if storey.is_a("IfcBuildingStorey"):
                    elevation = getattr(storey, 'Elevation', 0.0)
                    return elevation, getattr(storey, 'Name', 'Unknown')
        return 0.0, "Unknown"

    def get_shape_geometry(self, space, spacing, min_offset):
        settings = ifcopenshell.geom.settings()
        settings.set("USE_WORLD_COORDS", True)
        settings.set("USE_PYTHON_OPENCASCADE", True)

        extracted_points = []

        try:
            shape = ifcopenshell.geom.create_shape(settings, space)
            brep_shape = shape.geometry

            bbox = Bnd_Box()
            brepbndlib.Add(brep_shape, bbox)
            xmin, ymin, zmin, xmax, ymax, zmax = bbox.Get()

            classifier = BRepClass3d_SolidClassifier(brep_shape)

            x_coords = np.arange(xmin, xmax, spacing)
            y_coords = np.arange(ymin, ymax, spacing)

            for x in x_coords:
                for y in y_coords:
                    floor_point = gp_Pnt(x, y, zmin + 0.01)
                    classifier.Perform(floor_point, 1e-6)
                    if classifier.State() != TopAbs_IN:
                        continue

                    z_coords = np.arange(zmin + spacing, zmax, spacing)
                    for z in z_coords:
                        point = gp_Pnt(x, y, z)
                        classifier.Perform(point, 1e-6)
                        if classifier.State() == TopAbs_IN:
                            extracted_points.append((x, y, z))

            # Applica buffer zone
            offset_m = min_offset / 1000.0
            filtered_points = [
                (x, y, z) for x, y, z in extracted_points
                if (x > xmin + offset_m and x < xmax - offset_m and
                    y > ymin + offset_m and y < ymax - offset_m and
                    z > zmin + offset_m and z < zmax - offset_m)
            ]

            return filtered_points

        except Exception as e:
            return []

    def configure(self, configure_context, input_schema_1):
        return None

    def execute(self, exec_context, input_1):
        df = input_1.to_pandas()

        if df.empty:
            raise ValueError("The input table is empty.")

        ifc_path = df[self.path_column].iloc[0]

        if not os.path.exists(ifc_path):
            raise ValueError(f"File not found: {ifc_path}")

        ifc_file = ifcopenshell.open(ifc_path)
        spaces = ifc_file.by_type("IfcSpace")

        data = []

        for space in spaces:
            try:
                elevation, level_name = self.get_storey_elevation(space, ifc_file)
                long_name = getattr(space, "LongName", "Unknown")

                points = self.get_shape_geometry(space, self.spacing, self.min_offset_mm)

                for x, y, z in points:
                    data.append([x * 1000, y * 1000, z * 1000, space.GlobalId, level_name, long_name])
            except Exception:
                continue

        result_df = pd.DataFrame(data, columns=["X", "Y", "Z", "GlobalID", "Level", "LongName"])
        return knext.Table.from_pandas(result_df)