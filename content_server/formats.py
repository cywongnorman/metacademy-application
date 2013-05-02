# -*- coding: utf-8 -*-
import json
import os
import re
import sys
import pdb

from global_resources import NODE_COMPREHENSION_KEY, NODE_DEPENDENCIES, NODE_RESOURCES, WIKI_SUMMARY_PREFIX, WIKI_SUMMARY, NODE_SUMMARY, NODE_TITLE, NODE_SEE_ALSO

import graphs
import resources

WRAP_WIDTH = 12

class Missing:
    pass

def read_text_db(instr, fields, list_fields={}, require_all=True):
    items = []
    new_item = True
    curr = {}

    # Fields without default values indicate required fields
    fields = dict(fields)
    for k, v in fields.items():
        if not isinstance(v, tuple):
            fields[k] = (v, Missing)
    
    for line_ in instr:
        line = line_.strip()

        if line == '':
            new_item = True
            continue

        pos = line.find(':')
        if pos == -1:
            raise RuntimeError('Error reading line: %s' % line)
        field = line[:pos]
        value = line[pos+1:].strip()

        if new_item:
            curr = {}
            items.append(curr)
            for field_name, (tp, default) in fields.items():
                curr[field_name] = default

        if field in fields:
            tp, _ = fields[field]
            curr[field] = tp(value)
        elif field in list_fields:
            tp = list_fields[field]
            if field not in curr:
                curr[field] = []
            curr[field].append(tp(value))
        else:
            raise RuntimeError('Unknown field: %s' % field)

        new_item = False

    # Check that all required fields were filled
    for item in items:
        for field, value in item.items():
            if value is Missing:
                if require_all:
                    raise RuntimeError('Missing field %s for item %r' % (field, item))
                else:
                    del item[field]

    return items


def normalize_input_tag(itag):
    """Make sure node id (tags) only have valid characters and are in a common format"""
    return re.sub(r'[^a-z0-9]', '_', itag.strip().lower()).replace('-','_')

def remove_empty_keys(d):
    d = dict(d)
    for k, v in d.items():
        if v is None or v == []:
            del d[k]
    return d

def parse_list(s, sep):
    parts = s.split(sep)
    parts = [p.strip() for p in parts]
    return parts



############################ read nodes as directories #########################

def read_node(content_path, tag, assert_exists=False):
    """Read a Node object from a directory which optionally contains title.txt,
    dependencies.txt, key.txt, references.txt, summary.txt, and see-also.txt."""
    # TODO: normalize string cleaning (get rid of double quotes that mess up json)
    full_path = os.path.join(content_path, 'nodes', tag)

    ### process title
    title_file = os.path.join(full_path, NODE_TITLE)
    if os.path.exists(title_file):
        title = open(title_file).readlines()[0].strip()
    else:
        if assert_exists:
            raise RuntimeError('%s/%s does not exist' % (tag, NODE_TITLE))
        title = None

    ### process summary
    summary_file = os.path.join(full_path, NODE_SUMMARY)
    wiki_summary_file = os.path.join(full_path, WIKI_SUMMARY)
    summary = ""
    usewiki = False
    sfile = None
    if os.path.exists(summary_file):
        sfile = summary_file
    elif os.path.exists(wiki_summary_file):
        sfile = wiki_summary_file
        usewiki = True

    if sfile:
        summary = unicode(open(sfile).read(), 'utf-8')

    if usewiki and len(summary):
        summary = "%s%s" % (WIKI_SUMMARY_PREFIX, summary) # TODO should we use a wiki flag instead?

    # process resources
    resources_file = os.path.join(full_path, NODE_RESOURCES)
    if os.path.exists(resources_file):
        fields = dict(resources.RESOURCE_FIELDS)
        fields['source'] = str
        list_fields = dict(resources.RESOURCE_LIST_FIELDS)
        node_resources = read_text_db(open(resources_file), fields, list_fields, require_all=False)
        node_resources = map(remove_empty_keys, node_resources)
    else:
        node_resources = []
    
    

    ### process comprehension key
    ckey_file = os.path.join(full_path, NODE_COMPREHENSION_KEY)
    ckeys = []
    if os.path.exists(ckey_file):
        with open(ckey_file) as ckey_entries:
            for line in ckey_entries:
                line = line.strip()
                if len(line) > 0:
                    ckeys.append({"text":line})

    ### process dependencies
    dependencies_file = os.path.join(full_path, NODE_DEPENDENCIES)
    if os.path.exists(dependencies_file):
        fields = {'tag': normalize_input_tag,
                  'reason': (str, None),
                  }
        dependencies_dicts = read_text_db(open(dependencies_file), fields)
        dependencies = [graphs.Dependency(d['tag'], tag, d['reason'])
                        for d in dependencies_dicts]
    else:
        if assert_exists:
            raise RuntimeError('%s/%s does not exist' % (tag, NODE_DEPENDENCIES))
        dependencies = []
    
    ### process see-also
    see_also_file = os.path.join(full_path, NODE_SEE_ALSO)
    pointers = ""
    if os.path.exists(see_also_file):
        pointers = open(see_also_file).read()
        # for line_ in open(see_also_file):
        #     line = line_.strip()

        #     m = re.match(r'(.*)\[(.*)\]', line)
        #     if m:
        #         blurb = m.group(1).strip()
        #         to_tag = normalize_input_tag(m.group(2))
        #         ptr = graphs.Pointer(tag, to_tag, blurb)
        #         pointers.append(ptr)
    elif assert_exists:
        raise RuntimeError('%s/%s does not exist' % (tag, NODE_SEE_ALSO))
    return graphs.Node(
        {'tag': tag, 'resources': node_resources, 'title': title, 'summary': summary, 'dependencies': dependencies,
         'pointers': pointers, 'ckeys': ckeys})


def read_nodes(content_path, onlytitle=False):
    """Read all the nodes in a directory and return a dict mapping tags to Node objects."""
    nodes_path = os.path.join(content_path, 'nodes')
    tags = map(normalize_input_tag,_filter_non_nodes(os.listdir(nodes_path)))
    if onlytitle:
        return tags
    else:
        nodes = [read_node(content_path, tag) for tag in tags]
        return {node.tag: node for node in nodes}


def _filter_non_nodes(tags):
    return filter(lambda(x): x[0] != '.', tags) # remove hidden files from list


def check_format(content_path):
    nodes_path = os.path.join(content_path, 'nodes')
    tags = map(normalize_input_tag,os.listdir(nodes_path))
    # make sure files exist and are formatted correctly
    nodes = []
    for tag in tags:
        try:
            nodes.append(read_node(content_path, tag, assert_exists=True))
        except RuntimeError as e:
            print e

    # make sure tags do not have spaces
    for node in nodes:
        if re.search(r'\s', node.tag):
            print 'Node tag "%s" contains whitespace' % node.tag
        for d in node.dependencies:
            if re.search(r'\s', d.from_tag):
                print 'Node "%s" has dependency "%s" which contains whitespace' % (node.tag, d.from_tag)
        for p in node.pointers:
            if re.search(r'\s', p.to_tag):
                print 'Node "%s" has forward link "%s" which contains whitespace' % (node.tag, p.to_tag)


################################# write .dot files #############################

def underscorify(s):
    """Convert a string to a form that can be used in filenames, URLs, etc. by making everything
    lowercase and replacing non-letters with underscores."""
    temp = s.lower()
    temp = re.sub(r'[^a-z ]', ' ', temp)
    temp = temp.strip()
    return re.sub(r'\W+', '_', temp)

def wrap(s, width):
    """Wrap a long string to avoid elongated graph nodes."""
    if s is None:
        return ''

    parts = s.split()
    result = ''
    total = 0
    for p in parts:
        result += p
        total += len(p)
        if total > width:
            result += '\\n'
            total = 0
        else:
            result += " "
            total += 1
    return result


def write_graph_dot(nodes, graph, outstr=None):
    if outstr is None:
        outstr = sys.stdout

    print >> outstr, 'digraph G {'

    for tag, node in nodes.items():
        usetag = tag
        print >> outstr, '    %s [label="%s"];' % (usetag, wrap(node.title, WRAP_WIDTH))

    for parent, child in graph.edges:
        print >> outstr, '    %s -> %s;' % (parent, child)

    print >> outstr, '}'


#################################### JSON ######################################

def node_to_json(nodes, tag, user_nodes=None):
    node = nodes[tag]
    return json.dumps(node.as_dict(user_nodes=user_nodes))

def write_graph_json(nodes, graph, resource_dict=None, outstr=None, user_nodes=None):
    if outstr is None:
        outstr = sys.stdout

    items = {'nodes' : {node.tag: node.as_dict(user_nodes=user_nodes) for node in nodes.values()}}

    if resource_dict is not None:
        resrc_keys = set(
            [rsrc
             for rlist in [nde.get_resource_keys() for nde in nodes.values() if nde.resources]
             for rsrc in rlist
             if rsrc in resource_dict])
        res_dict = {key: remove_empty_keys(resource_dict[key]) for key in resrc_keys}
        items['node_resources'] = res_dict

    json.dump(items, outstr)

def node_resources(node, resource_defaults):
    return [resources.add_defaults(r, resource_defaults) for r in node.resources]

def node_resources_json(node, resource_dict):
    return json.dumps(node_resources(node, resource_dict))


############################### User data ######################################

def node_user_data_file(user_content_path, tag):
    return os.path.join(user_content_path, 'nodes', '%s.json' % tag)

def read_user_nodes(user_content_path):
    user_nodes_path = os.path.join(user_content_path, 'nodes')
    if not os.path.exists(user_nodes_path):
        return {}

    nodes = {}
    fnames = os.listdir(user_nodes_path)
    for fname in fnames:
        full_path = os.path.join(user_nodes_path, fname)
        tag, ext = fname.split('.')
        assert ext == 'json'
        nodes[tag] = json.load(open(full_path))

    return nodes

def check_node_user_data_format(jdata):
    pass   # TODO

def write_node_user_data(user_content_path, tag, jdata):
    user_nodes_path = os.path.join(user_content_path, 'nodes')
    if not os.path.exists(user_nodes_path):
        os.mkdir(user_nodes_path)
    fname = node_user_data_file(user_content_path, tag)
    json.dump(jdata, open(fname, 'w'))






    
