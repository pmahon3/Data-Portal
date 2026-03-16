import logging

from treelib import Tree

logger = logging.getLogger('app')


def convert_file_tree_to_dict(tree: Tree) -> list[dict]:
    """
    Convert a file tree to a dictionary.

    :param tree: The file tree to convert.
    :type tree: Tree
    :return: The converted file tree as a dictionary.
    :rtype: list[dict]
    """
    tree_data = []
    for node in tree.all_nodes():
        if node.tag != 'root':  # Skip the 'root' node
            parent = tree.parent(node.identifier)
            # If the parent is 'root', treat this node as a top-level node
            parent_id = '#' if parent is None or parent.tag == 'root' else parent.identifier
            tree_data.append(
                {"id": node.identifier, "parent": parent_id, "text": node.tag, "li_attr": {"data-id": node.identifier}}
            )
    return tree_data

