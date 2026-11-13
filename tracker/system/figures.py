import base64
from io import BytesIO

import matplotlib.pyplot as plt
from matplotlib.figure import Figure


def render_svg_base64(fig: Figure) -> str:
    """Render the figure as a base64 encoded svg and close it."""
    try:
        buff = BytesIO()
        fig.savefig(buff, format="svg")
        return base64.b64encode(buff.getvalue()).decode("utf-8")
    finally:
        plt.close(fig)
