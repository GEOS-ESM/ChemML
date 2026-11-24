# Deepsensor Run materials

This folder contains materials related to using the [Deepsensor python package](https://alan-turing-institute.github.io/deepsensor/index.html) for fusing multi-source air quality data related to ASIA-AQ.

[Installation instructions for the Deepsensor package and dependencies.](https://alan-turing-institute.github.io/deepsensor/getting-started/installation.html)

Material was developed for use on NCCS Discover.

- `ASIAAQ_Deepsensor_Run.py`: Python code for running an analysis on discover; takes setting from `json` files created by `Deepsensor_Batch_Setup.ipynb`.
- `Deepsensor_Batch_Setup.ipynb`: Jupyter Notebook for setting up a batch of runs of the `ASIAAQ_Deepsensor_Run.py` code, e.g., a cross-validation series with common settings.
- `Deepsensor_Batch_Result_Analysis.ipynb`: Jupyter Notebook for loading and interpreting results of a batch of runs.
