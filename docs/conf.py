# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

project = 'libcsound'
copyright = '2024, Eduardo Moguillansky'
author = 'Eduardo Moguillansky'

import os
import sys
sys.path.insert(0, os.path.abspath('../'))


# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = [
    'sphinx.ext.autodoc',
    'sphinx_automodapi.automodapi',
    'sphinx.ext.napoleon',
    'sphinx_autodoc_typehints',
    'sphinx.ext.viewcode',
    'sphinx.ext.autosummary',
    # 'sphinx_automodapi.smart_resolver',
    'autodocsumm',
    'nbsphinx',
]

templates_path = ['_templates']
exclude_patterns = ['_build', 'Thumbs.db', '.DS_Store']



# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_theme = 'sphinx_book_theme'
html_static_path = ['_static']

html_theme_options = {
    "show_navbar_depth": 3,
    "max_navbar_depth": 5,
    "show_toc_level": 2,
    "use_fullscreen_button": False,
    
}

# Disable having a separate return type row
napoleon_use_rtype = False

# typehints_fully_qualified = False
typehints_document_rtype = True

# Autodoc
# autodoc_member_order = 'bysource'


html_css_files = [
    'custom.css',
]
