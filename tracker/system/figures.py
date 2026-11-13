import base64
from io import BytesIO

from matplotlib.axes import Axes
from matplotlib.figure import Figure


FIGURE_SIZE = (12, 10)


def create_figure() -> tuple[Figure, Axes]:
    """Create a figure outside pyplot, so nothing keeps it alive once it is dropped."""
    fig = Figure(figsize=FIGURE_SIZE)
    return fig, fig.subplots()


def render_svg_base64(fig: Figure) -> str:
    buff = BytesIO()
    fig.savefig(buff, format="svg")
    return base64.b64encode(buff.getvalue()).decode("utf-8")
