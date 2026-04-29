import tree_sitter_languages
parser = tree_sitter_languages.get_parser("python")
code = b"def foo():\n  pass"
tree = parser.parse(code)
print(tree.root_node.sexp())
