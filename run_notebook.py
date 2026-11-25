"""Execute the notebook in place (alternative to opening Jupyter and clicking Run All)."""
from pathlib import Path
import nbformat
from nbclient import NotebookClient

nb_path = Path(__file__).resolve().parents[1] / "notebooks" / "truck_superapp_product_analytics.ipynb"
nb = nbformat.read(nb_path, as_version=4)
NotebookClient(nb, timeout=1200, kernel_name="python3", resources={"metadata": {"path": str(nb_path.parent)}}).execute()
nbformat.write(nb, nb_path)
print("executed:", nb_path)
