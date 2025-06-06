# Building Information Modelling (BIM) Extension for KNIME (IFC)

  
![image](https://github.com/acpvarchitects/CVP.App.Knime.BIM/assets/26569178/f3c38376-4329-4d02-94d6-4d91beb9969f)



This extension has been developed by the ACPV ARCHITECTS in-house unit ACPVX. The goal was to harvesting information from all the IFC Models of our projects in an easy way.

It's a initial work in progress repository which will be integrated with other nodes are they are developed

## What's New in Version 2.0.0

This new version includes several major improvements:

- Refactored Python nodes into separate modules for better organization
- Extended IFCReader functionality to support IFC4 schema
- Added new custom KNIME nodes for IFC processing:
  - IFC Reader: Reads IFC2x3 and IFC4 files, extracting elements with properties
  - IFC Building Info: Extracts information about the IfcBuilding entity
  - IFC Element Centroids: Computes 3D bounding box centroids for IFC elements
  - IFC Door Offset XYZ: Generates offset points for door elements
  - IFC Room Points: Creates interior points within room volumes
  - IFC Intersection: Performs geometric intersection operations

## Installation

This version requires KNIME Analytics Platform version 5.1.1 or later.

(new!) From the KNIME Hub: https://hub.knime.com/emilianocapasso/extensions/cvp.app.knime.features.bim/latest

From this repository:
1. downloading the zip in the Latest [Release](https://github.com/acpvarchitects/CVP.App.Knime.BIM/releases/tag/1.0.0)
2. unzip the file into a folder
3. go to File > Preferences > Install/Updates > Available Software Sites" and add the location of the unzipped folder into local Software Site
 ![image](https://github.com/acpvarchitects/CVP.App.Knime.BIM/assets/26569178/7a502a45-2fd3-4bff-80b1-6d7e8dca3264)
4. File > Install KNIME Extensions and you should see "Building Information Modelling Extension for KNIME (IFC) 
   ![image](https://github.com/acpvarchitects/CVP.App.Knime.BIM/assets/26569178/f7affae4-5a6a-4687-a0a3-822bc522c53f)
   
5. Select and click next
   
 ![image](https://github.com/acpvarchitects/CVP.App.Knime.BIM/assets/26569178/05c9a46d-e1c8-4b04-82b1-4d6d29a7828a)
 
6. Trust the unsigned content

 ![image](https://github.com/acpvarchitects/CVP.App.Knime.BIM/assets/26569178/e3c37f66-da80-4341-a3f4-f4296c94605f)
 
7. Once the installation is complete, you should find the Nodes here

![image](https://github.com/acpvarchitects/CVP.App.Knime.BIM/assets/26569178/383d618c-9230-4276-9895-e1b2f63e5777)
