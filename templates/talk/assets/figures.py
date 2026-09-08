#!/usr/bin/env python3
"""Generate every figure this talk needs. Deterministic; one palette; one aspect ratio.
Run from anywhere: python3 pieces/<slug>/assets/figures.py"""
import os
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
rng = np.random.default_rng(7)
INK, ACCENT, COOL, PAPER = '#1f1f1f', '#d1602b', '#4a6fa5', '#fbfaf7'
plt.rcParams.update({'figure.facecolor': PAPER, 'axes.facecolor': PAPER, 'text.color': INK,
                     'axes.edgecolor': INK, 'axes.labelcolor': INK, 'xtick.color': INK,
                     'ytick.color': INK, 'font.size': 13, 'axes.spines.top': False,
                     'axes.spines.right': False})

def save(fig, name):
    fig.savefig(os.path.join(HERE, name), dpi=200, bbox_inches='tight'); plt.close(fig)
    print('wrote', name)

# def fig1():
#     fig, ax = plt.subplots(figsize=(12, 6.75))
#     ...
#     save(fig, 'fig1.png')

if __name__ == '__main__':
    pass
