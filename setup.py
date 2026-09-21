from setuptools import setup, find_packages

setup(
    name="abraflexi-mcp-server",
    version="1.5.2",
    description="A comprehensive MCP server for AbraFlexi integration",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    author="Vítězslav Dvořák",
    author_email="info@vitexsoftware.cz",
    url="https://github.com/VitexSoftware/abraflexi-mcp-server",
    packages=find_packages(),
    include_package_data=True,
    install_requires=[
        "fastmcp>=2.12.4",
        "python-abraflexi>=1.0.0",
        "python-dotenv>=1.1.1",
    ],
    entry_points={
        "console_scripts": [
            "abraflexi-mcp=abraflexi_mcp_server.server:main",
        ],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Intended Audience :: System Administrators",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Topic :: Office/Business :: Financial :: Accounting",
    ],
    python_requires=">=3.10",
)
