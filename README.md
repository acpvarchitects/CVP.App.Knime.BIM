# Python Extension Tutorials

A collection of tutorials to develop Python extensions.

## Contents
- [Python Extension Tutorials](#python-extension-tutorials)
  - [Contents](#contents)
  - [Prerequisites](#prerequisites)
  - [Tutorial 1: Writing your first Python node from scratch](#tutorial-1-writing-your-first-python-node-from-scratch)

## Prerequisites
To get started with developing Python Node Extensions, you need to have `conda` installed (via Anaconda or Miniconda). Here is the quickest way:

1. Go to [https://docs.conda.io/en/latest/miniconda.html](https://docs.conda.io/en/latest/miniconda.html)
2. Download the appropriate installer for your OS.
3. For Windows and macOS: run the installer executable.
4. For Linux: execute the script in terminal (see [here](https://conda.io/projects/conda/en/latest/user-guide/install/linux.html) for help)


Download this directory (`basic`). In the `basic` folder, you should see the following files:
```
.
├── tutorial_extension
│   │── icon.png
│   │── knime.yml
│   │── LICENSE.TXT
│   └── my_extension.py
├── config.yml
├── Example_with_Python_node.knwf
└── README.md
```

## Tutorial 1: Writing your first Python node from scratch

This is a quickstart guide that will walk you through the essential steps of writing and running your first Python Node Extension. We will use `tutorial_extension` as the basis. The steps of the tutorial requiring modification of the Python code in `my_extension.py` have corresponding comments in the file, for convenience.

For an extensive overview of the full API, please refer to the [Defining a KNIME Node in Python: Full API](#defining-a-knime-node-in-python-full-api) section, as well as our [Read the Docs page](https://knime-python.readthedocs.io/en/latest/content/content.html#python-extension-development).

1. Install the KNIME Analytics Platform version 4.6.0 or higher, or a Nightly version (if Nightly before the release of 4.6.0, use the master update site. See [here](https://knime-com.atlassian.net/wiki/spaces/SPECS/pages/1369407489/How+to+find+download+install+update+and+use+KNIME+Nightly+Builds+for+Verification.) for help with Nightlies and update sites.)

2. Go to _File_ -> _Install KNIME Extensions…_, enter "Python" in the search field, and look for `KNIME Python Node Development Extension (Labs)`. Alternatively you can manually navigate to the `KNIME Labs Extensions` category and find the extension there. Select it and proceed with installation.

3. The `tutorial_extension` will be your new extension. Familiarise yourself with the files contained in that folder, in particular:
    - `knime.yml`, which contains important metadata about your extension.
    - `my_extension.py`, which contains Python definitions of the nodes of your extension.
    - `config.yml`, just outside of the folder, contains information that binds your extension and the corresponding `conda`/Python environment with KNIME Analytics Platform.

4. Create a `conda`/Python environment containing the [`knime-python-base`](https://anaconda.org/knime/knime-python-base) metapackage, together with the node development API [`knime-extension`](https://anaconda.org/knime/knime-extension), and [`packaging`](https://anaconda.org/anaconda/packaging). If you are using `conda`, you can create the environment by running the following command in your terminal (macOS/Linux) or Anaconda Prompt (Windows):

    ```console
    conda create -n my_python_env python=3.9 packaging knime-python-base knime-extension -c knime -c conda-forge
    ```
    If you would like to install `knime-python-base` and `packaging` into an already existing environment, you can run the following command _from within that environment_:

    ```console
    conda install knime-python-base knime-extension packaging -c knime -c conda-forge
    ```

    Note that you __must__ append both the `knime` and `conda-forge` channels to the commands in order for them to work.

5. Edit the `config.yml` file located just outside of the `tutorial_extension` (for this example, the file already exists with prefilled fields and values, but you would need to manually create it for future extensions that you develop). The contents should be as follows:

    ```
    <extension_id>:
        src: path/to/folder/of/template
        conda_env_path: path/to/my_python_env
        debug_mode: true
    ```
    where:

    - `<extension_id>` should be replaced with the `group_id` and `name` values specified in `knime.yml`, combined with a dot.
    
    For our example extension, the value for `group_id` is `org.knime`, and the value for `name` is `fluent_extension`, therefore the `<extension_id>` placeholder should be replaced with `org.knime.fluent_extension`.
    
    - the `src` field should specify the path to the `tutorial_extension` folder.

    - similarly, the `conda_env_path` field should specify the path to the `conda`/Python environment created in Step 4. To get this path, run the `conda env list` command in your Terminal/Anaconda Prompt, and copy the path next to the appropriate environment (`my_python_env` in our case).

    - the `debug_mode` is an optional field, which, if set to `true`, will tell KNIME Analytics Platform to use the latest changes in the `configure` and `execute` methods of your Python node class whenever those methods are called.

6. We need to let KNIME Analytics Platform know where the `config.yml` is in order to allow it to use our extension and its Python environment. To do this, you need to edit the `knime.ini` of your KNIME Analytics Platform installation, which is located at `<path-to-your-KAP>/Contents/Eclipse/knime.ini`.

    Append the following line to the end, and modify it to have the correct path to `config.yml`: 
    ```
    -Dknime.python.extension.config=path/to/your/config.yml
    ```

7. Start your KNIME Analytics Platform.

8. The "My Template Node" node should now be visible in the Node Repository.

9. Import and open the `Example_with_Python_node.knwf` workflow, which contains our test node:  
    1. Get familiar with the table.
    2. Study the code in `my_extension.py` and compare it with the node you see in KNIME Analytics Platform. In particular, understand where the node name and description, as well as its inputs and outputs, come from.
    3. Execute the node and make sure that it produces an output table.

10. Build your first configuration dialog!

    In `my_extension.py`, uncomment the definitions of parameters (marked by the "Tutorial Step 10" comment). Restart your KNIME Analytics Platform,, then drag&drop the node again into the workflow and you should be able to double-click the node and see configurable parameters - congrats!
    
    Take a minute to see how the names, descriptions, and default values compare between their definitions in `my_extension.py` and the node dialog.

11. Add your first port!

    To add a second input table to the node, follow these steps (marked by the "Tutorial Step 11" comment, you will need to restart):
    1. Uncomment the `@knext.input_table` decorator.
    2. Change the `configure` method's definition to reflect the changes in the schema.
    3. Change the `execute` method to reflect the addition of the second input table.

12. Add some functionality to the node!

    With the following steps, we will append a new column to the first table and output the new table (the lines requiring to be changed are marked by the "Tutorial Step 12" comment):

    1. To inform downstream nodes of the changed schema, we need to change it in the return statement of the `configure` method; for this, we append metadata about a column to the output schema.
    2. Everything else is done in the `execute` method:
        - we transform both input tables to pandas dataframes and append a new column to the first dataframe
        - we transform that dataframe back to a KNIME table and return it

13. Use your parameters!

    In the `execute` method, uncomment the lines marked by the "Tutorial Step 13" comment:
    
    Use a parameter to change some table content; we will add the value of the `double_param` parameter to every cell of a column.

14. Start logging and setting warnings!
    
    In the `execute` method, uncomment the lines marked by the "Tutorial Step 14" comment:
    Use the LOGGER functionality to inform users, or for debugging.
    Use the `execute_context.set_warning("A warning")` to inform the user about unusual behaviour
    If you want the node to fail, you can use `raise ValueError("This node failed just because")`

15.  Congratulations, you have built your first functioning node entirely in Python!

