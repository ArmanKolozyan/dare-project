import json
import secrets
import unittest
from hashlib import sha256
from nacl.signing import SigningKey, VerifyKey


def hex_hash(byte_str):
    """Returns the SHA-256 hash of byte string ``byte_str``, encoded as hexadecimal."""
    return sha256(byte_str).hexdigest()

def sign_msg(signing_key, message):
    """
    Takes a message ``message`` (given as a dictionary), JSON-encodes it, and signs it using
    ``signing_key``. Returns a byte string in which the first 32 bytes are the public key, the next
    64 bytes are the signature, and the rest is the JSON-encoded message.
    """
    public_key = signing_key.verify_key.encode()
    signed_msg = signing_key.sign(json.dumps(message).encode('utf-8'))
    return public_key + signed_msg

def verify_msg(signed_msg):
    """
    Takes a byte string of the form generated by ``sign_msg()``, checks the validity of the
    signature, and parses the JSON into a dictionary. The public key that signed the message is
    added to the dictionary under the key ``signed_by`` (as a hexadecimal string). Raises an
    exception if the signature is not valid.
    """
    public_key = VerifyKey(signed_msg[0:32]) # first 32 bytes are pubkey
    verified = json.loads(public_key.verify(signed_msg[32:]))
    return {**verified, 'signed_by': signed_msg[0:32].hex()}

def create_op(signing_key):
    """Returns a group creation operation signed by ``signing_key``."""
    return sign_msg(signing_key, {'type': 'create', 'nonce': secrets.token_hex(16)})

def add_op(signing_key, added_key, preds):
    """Returns an operation signed by ``signing_key``, which adds ``added_key`` to the group.
    ``preds`` is a list of hashes of immediate predecessor operations."""
    return sign_msg(signing_key, {'type': 'add', 'added_key': added_key, 'preds': preds})

def remove_op(signing_key, removed_key, preds):
    """Returns an operation signed by ``signing_key``, which removes ``removed_key`` from the group.
    ``preds`` is a list of hashes of immediate predecessor operations."""
    return sign_msg(signing_key, {'type': 'remove', 'removed_key': removed_key, 'preds': preds})

def post_op(signing_key, message, preds):
    """Returns an operation signed by ``signing_key``, which adds a ``message`` to the group.
    ``preds`` is a list of hashes of immediate predecessor operations."""
    return sign_msg(signing_key, {'type': 'post', 'message': message, 'preds': preds})

def interpret_ops(ops):
    """
    Takes a set of access control operations and computes the currently authorised set of users.
    Throws an exception if something isn't right.
    """
    # Check all the signatures and parse all the JSON
    ops_by_hash = {hex_hash(op): verify_msg(op) for op in ops}
    parsed_ops = ops_by_hash.values()

    # Every op must be one of the expected types 
    # (added post for exercise 2)
    if any(op['type'] not in {'create', 'add', 'remove', 'post'} for op in parsed_ops):
        raise Exception('Every op must be either create, add, remove, or post')
    if any('added_key' not in op for op in parsed_ops if op['type'] == 'add'):
        raise Exception('Every add operation must have an added_key')
    if any('removed_key' not in op for op in parsed_ops if op['type'] == 'remove'):
        raise Exception('Every remove operation must have a removed_key')
    # added for exercise 2:
    if any('message' not in op for op in parsed_ops if op['type'] == 'post'):
        raise Exception('Every post operation must have a message')



    # Hash graph integrity: every op except the initial creation must reference at least one
    # predecessor operation, and all predecessors must exist in the set
    if any(len(op['preds']) == 0 for op in parsed_ops if op['type'] != 'create'):
        raise Exception('Every non-create op must have at least one predecessor')
    if any(pred not in ops_by_hash
           for op in parsed_ops if op['type'] != 'create'
           for pred in op['preds']):
        raise Exception('Every hash must resolve to another op in the set')

    # Get the public key of the group creator
    create_ops = [(hash, op) for hash, op in ops_by_hash.items() if op['type'] == 'create']
    if len(create_ops) != 1:
        raise Exception('There must be exactly one create operation')

    # current group members are computed by the algorithm from the paper
    return compute_membership_and_messages(ops)

def compute_membership_and_messages(ops): 
    ops_by_hash = {hex_hash(op): verify_msg(op) for op in ops}
    seniority = compute_seniority(ops_by_hash) # of the form {pk : depth(add_op_of_pk), hash(add_op_of_pk)}
    auth_graph = authority_graph(ops_by_hash) # of the form {(add/create_or_rem_op_of_pk, (member, pk)) or (op1, op2)}
    # member_nodes filters out the (op1, op2) - only the ones of the form (add/create_or_rem_op_of_pk, (member, pk)) 
    member_nodes = {member_pk for _, member_pk in auth_graph if isinstance(member_pk, tuple) and member_pk[0] == 'member'}
    # for exercise two:
    message_nodes = { post_hash: post_info for post_hash, post_info  in ops_by_hash.items()  if post_info['type'] == 'post' } 
    cycles = uniquify([cycle for node in member_nodes for cycle in find_cycles(auth_graph, node, [])]) # of the form [[ op1_hash, op2_hash, ... , op1_hash, ...] .. ] ; uniquify because python does not allow sets in sets, have to work with frozen sets etc.
    # By default max will compare the items by the first index. 
    # If the first index is the same then it'll compare the second index - https://stackoverflow.com/questions/18296755/python-max-function-using-key-and-lambda-expression
    # and op as third argument just as a trick to still keep the op
    # the (member, pk) vertices do not have outgoing edges - by definition
    drop = { max([(seniority[subject(ops_by_hash[op_hash])], op_hash) for op_hash in cycle])
                for cycle in cycles } # of the form (hash(add_op_of_pk_signing), hash(op))
    # the n1,n2 where neither the n1 nor the n2 are in drop (but drop is a 2-tuple, so we need to filter and see it is empty - not any(x) -> there is no x, x is empty)
    auth_graph2 = { (n1, n2) for n1, n2 in auth_graph if (not any(filter(lambda tuple: tuple[1] == n1, drop))) and (not any(filter(lambda tuple: tuple[1] == n2, drop)))}

    # compute_validity starting from the nodes without outgoing edges (member, pk) and the message nodes
    valid = {}
    for node in [*member_nodes, *message_nodes]:
        valid = compute_validity(ops_by_hash, auth_graph2, node, valid)
 
    return { 'members' : { pk for _, pk in member_nodes if valid['member', pk] },
             'valid_messages' : { post_info['message'] for post_hash, post_info in message_nodes.items() if valid[post_hash]}}

def subject(op):
    # you return the public key from the device that *does* the action
    if op['type'] in ['create', 'add', 'remove', 'post']:
        return op['signed_by']

def compute_seniority(ops_by_hash) :
    # Get the set of successor hashes for each op
    successors = {}
    for hash, op in ops_by_hash.items():
        for pred in op.get('preds', []):
            successors[pred] = successors.get(pred, set()) | {hash}

    # operations without causal successor 
    # aka the most recent operation
    # in pseudocode, it was the op - but we need to use the hash because python dictionaries do not want other dictionaries as the key
    heads = [hash  for hash, op in ops_by_hash.items() if not successors.get(hash, set())]
    added, depth = {}, {}
    for head in heads:
        added, depth = check_graph(ops_by_hash, head, added, depth)

    # return mapping from public key to seniority (depth, hash) 
    # depth is the longest path in the hash DAG, hash is only used as a tiebreaker
    # aka for that pk, find all "add operations" and pick the min - min automatically first checks the first element of the tuple afterwards the second one as a tiebreaker
    return { pk: min([(depth[op_hash], op_hash) for pk2, op_hash in added if pk2 == pk]) for pk, _ in added}

# in the pseudocode, we needed depth to be op:number, but op is a dict, and we cannot have a dict as a key in another dict
# similar for the added, we cannot have a dict inside a set -> use the hash of the op
def check_graph(ops_by_hash, op_hash, added, depth):
    op = ops_by_hash[op_hash] 
    # op is part of depth: 
    if not isinstance(depth.get(op_hash, False), bool): 
        return added, depth
    # depth and added are empty, operation type is create
    elif not depth and not added and op['type'] == 'create' :
        return { (op['signed_by'] , op_hash)}, {op_hash : 0} # op['signed_by'] is the public key of the device 
    # operation type is add/remove/post and it has predecessors
    elif op['type'] in {'add', 'remove', 'post'} and op['preds']:
        maxDepth = 0
        for predecessor_hash in op['preds']:
            added, depth = check_graph(ops_by_hash, predecessor_hash, added, depth)
            maxDepth = max(maxDepth, depth.get(predecessor_hash, 0))
        # there does not exist an operation that came before that added the key that signs this operation:
        if not any([added_key == op['signed_by'] and precedes(ops_by_hash, add_op_hash, op) for added_key, add_op_hash in added]):
            Exception("Signing key was not yet added to the graph - check_graph")
        # if this is an "add" operation, add it to the "added":
        if op['type'] == 'add':
            added.add((op['added_key'], op_hash))
        depth.update({op_hash : maxDepth + 1})
        return (added, depth)
    else:
        Exception("Invalid graph - check_graph")


def authority_graph(ops_by_hash):
    """
    INPUT ops representing a hash DAG
    OUTPUT the set of edges of the authority graph
    -> edge from op1 to op2 if op1 may affect whether op2 is authorised
    this means adding additional edges 
    1) op1 adds the device with pk, op2 is a causally succeeding operation performed by device pk
    2) op1 removes the device with pk, op2 is performed by that device, AND op1 precedes op2 or they are concurrent
    REMARK: again, need to use the hash of the operation instead of the operation itself because python does not like dictionaries

    for exercise 2 only added that you do not need to add a member node if it is a post message
    """
    # idea: go over all ops, for each op
    ## check whether it is an add/create op -> (op1, (member, pk))
    ## go over all ops (2nd loop), for each op done by device pk
    ### (not) precedes op1, depending on op1
    authority_graph = set()
    for hash1, op1 in ops_by_hash.items():
        op1_type = op1['type']
        # if the operation is post, no additional edges must be added since it does not affect the authorisation of any public keys
        if op1_type != 'post':
            # get the correct p_k
            p_k = None
            if op1_type == 'create':
                p_k = op1['signed_by']; # for a created op, you want the creator
            elif op1_type == 'add':
                p_k = op1['added_key'] # for an add op, you want the p_k that is added
            elif op1_type == 'remove':
                p_k = op1['removed_key'] # for a remove op, you want the p_k of the removed device

            # add an edge between every operation that may affect the permissions associated with the device that has p_k
            authority_graph.add((hash1, ('member', p_k)))  
            # check for dependencies and add those as extra edges to the graph
            for hash2, op2 in ops_by_hash.items():
                if op2['signed_by'] == p_k: # the operations done by the device with p_k
                    if ((op1_type == 'create' or op1_type == 'add') and precedes(ops_by_hash, hash1, op2)) or (op1_type == 'remove' and not precedes(ops_by_hash, hash2, op1)) :
                        authority_graph.add((hash1, hash2))
    return authority_graph
    
def uniquify(lst_of_lsts):
    unique = {frozenset(lst) for lst in lst_of_lsts}
    return [list(set) for set in unique]

def find_cycles(authority_graph, node, path):
    # node can be (member, pk) or op_hash
    if node in path:
        # return a list with a list of all operations that come after the node in path -- lists because cannot do nested sets in python 
        return [path[path.index(node):]]
    else:
        preds = { op1 for op1, op2 in authority_graph if op2 == node} # all operations that causally precede the node 
        # return a set with sets of loops
        path = path + [node] 
        return [cycle for n in preds for cycle in find_cycles(authority_graph, n, path)]

def compute_validity(ops_by_hash, authority_graph, node, valid):
    # node is or of the form (member, pk) or of the form op_hash
    if node in valid:
        return valid
    if not isinstance(node, tuple):   # it is not the (member, pk) node -> it is an actual operation hash [extra condition was not there in the pseudocode but we need it]
        node_op = ops_by_hash[node]
        if node_op ['type'] == 'create':
            valid.update({node : True})
            return valid
    # compute validity for every operation from which there is an incoming edge into op
    op_prevs = []
    for prev, node2 in authority_graph:
        if node2 == node:
            valid = compute_validity(ops_by_hash, authority_graph, prev, valid)
            op_prevs += [prev] # predecessor of op
    op_hashes_incoming_edge_in_current_op = {prev for prev in op_prevs if valid[prev]}
    # there exists at least one add/create operation
    ## that is not overridden by a remove operation 
    # in the incoming edges 
    tmp_bool = False
    for add_op_hash in op_hashes_incoming_edge_in_current_op:
        add_op = ops_by_hash[add_op_hash]
        def filter_function(rem_op_hash):
            rem_op = ops_by_hash[rem_op_hash]
            return rem_op['type'] == 'remove' and precedes(ops_by_hash, add_op_hash, rem_op)
            # filter the remove operations that succeed the op, if none (not any) -> you found it!
        if (add_op['type'] in ['add', 'create']) and (not any(filter(filter_function, op_hashes_incoming_edge_in_current_op))) :
            tmp_bool = True
            break

    valid.update({node : tmp_bool})
    return valid

def precedes(ops_by_hash, op1_hash, op2):
    predecessors = op2.get('preds', []) # no predecessors when create
    return op1_hash in predecessors or any([precedes(ops_by_hash, op1_hash, ops_by_hash[predecessor]) for predecessor in predecessors])

class TestAccessControlList(unittest.TestCase):

    # Generate keys for all the participants
    private = {name: SigningKey.generate() for name in {'alice', 'bob', 'carol', 'dave'}}
    public = {name: key.verify_key.encode().hex() for name, key in private.items()}
    friendly_name = {public_key: name for name, public_key in public.items()}

    def test_add_remove(self):

        # Alice creates the group, adds Bob, and concurrently adds Carol, after both Alice removes Bob
        create = create_op(self.private['alice'])
        add_b = add_op(self.private['alice'], self.public['bob'], [hex_hash(create)])
        add_c = add_op(self.private['alice'], self.public['carol'], [hex_hash(create)])
        rem_b = remove_op(self.private['alice'], self.public['bob'], [hex_hash(add_b), hex_hash(add_c)])

        # Compute group membership
        interpretation_results = interpret_ops({create, add_b, add_c, rem_b})
        members = interpretation_results['members']
        valid_messages = interpretation_results['valid_messages']

        self.assertEqual({self.friendly_name[member] for member in members}, {'alice', 'carol'})
        self.assertEqual(valid_messages, set()) # no valid messages

    def test_paper_figure_2(self):

        # Alice creates the group, adds Bob and Carol one after the other, concurrently with the addition of Carol, Bob adds Dave
        create = create_op(self.private['alice'])
        add_b = add_op(self.private['alice'], self.public['bob'], [hex_hash(create)])
        add_c = add_op(self.private['alice'], self.public['carol'], [hex_hash(add_b)])
        add_d = add_op(self.private['bob'], self.public['dave'], [hex_hash(add_b)])

        # Compute group membership
        interpretation_results = interpret_ops({create, add_b, add_c, add_d})
        members = interpretation_results['members']
        valid_messages = interpretation_results['valid_messages']

        self.assertEqual({self.friendly_name[member] for member in members}, {'alice', 'bob', 'carol', 'dave'})
        self.assertEqual(valid_messages, set()) # no valid messages

    def test_paper_figure_3(self):

        # Alice creates the group, adds Bob, then removes Bob, and concurrently with the removal of Bob, bob adds Carol. 
        create = create_op(self.private['alice'])
        add_b = add_op(self.private['alice'], self.public['bob'], [hex_hash(create)])
        remove_b = remove_op(self.private['alice'], self.public['bob'], [hex_hash(add_b)])
        add_c = add_op(self.private['bob'], self.public['carol'], [hex_hash(add_b)])

        # Compute group membership
        interpretation_results = interpret_ops({create, add_b, remove_b, add_c})
        members = interpretation_results['members']
        valid_messages = interpretation_results['valid_messages']

        self.assertEqual({self.friendly_name[member] for member in members}, {'alice'})
        self.assertEqual(valid_messages, set()) # no valid messages

    def test_paper_figure_4(self):

        # Alice creates the group, adds Bob, then Bob adds Carol, afterwards Alice removes Bob
        create = create_op(self.private['alice'])
        add_b = add_op(self.private['alice'], self.public['bob'], [hex_hash(create)])
        add_c = add_op(self.private['bob'], self.public['carol'], [hex_hash(add_b)])
        remove_b = remove_op(self.private['alice'], self.public['bob'], [hex_hash(add_c)])

        # Compute group membership
        interpretation_results = interpret_ops({create, add_b, remove_b, add_c})
        members = interpretation_results['members']
        valid_messages = interpretation_results['valid_messages']

        self.assertEqual({self.friendly_name[member] for member in members}, {'alice', 'carol'})
        self.assertEqual(valid_messages, set()) # no valid messages

    def test_paper_figure_6(self):

        # cycle in the authority graph!
        # Alice creates the group, adds Bob, afterwards removes Bob. 
        # Concurrently with the removal of Bob, Bob adds Carrol - and after the addition of Carol, she removes Alice
        create = create_op(self.private['alice'])
        add_b = add_op(self.private['alice'], self.public['bob'], [hex_hash(create)])
        remove_b = remove_op(self.private['alice'], self.public['bob'], [hex_hash(add_b)])
        add_c = add_op(self.private['bob'], self.public['carol'], [hex_hash(add_b)])
        remove_a = remove_op(self.private['carol'], self.public['alice'], [hex_hash(add_c)])

        # Compute group membership
        interpretation_results = interpret_ops({create, add_b, remove_b, add_c, remove_a})
        members = interpretation_results['members']
        valid_messages = interpretation_results['valid_messages']

        self.assertEqual({self.friendly_name[member] for member in members}, {'alice'})
        self.assertEqual(valid_messages, set()) # no valid messages

    def test_mutual_removal(self):

        # Alice creates the group, she adds Bob, then Bob and Alice concurrently remove each other.  
        create = create_op(self.private['alice'])
        add_b = add_op(self.private['alice'], self.public['bob'], [hex_hash(create)])
        remove_b = remove_op(self.private['alice'], self.public['bob'], [hex_hash(add_b)])
        remove_a = remove_op(self.private['bob'], self.public['alice'], [hex_hash(add_b)])

        # Compute group membership
        interpretation_results = interpret_ops({create, add_b, remove_b, remove_a})
        members = interpretation_results['members']
        valid_messages = interpretation_results['valid_messages']

        self.assertEqual({self.friendly_name[member] for member in members}, {'alice'})
        self.assertEqual(valid_messages, set()) # no valid messages

    def test_mutual_removal_2(self):
        # to test the depth looks at the first add
        # Alice creates the group, then adds Bob, Bob removes Alice and then adds Alice again. Afterwards, Bob and Alice concurrently remove each other.
        # should be resolved according to greatest seniority, should still be Alice
        create = create_op(self.private['alice'])
        add_b = add_op(self.private['alice'], self.public['bob'], [hex_hash(create)])
        remove_a1 = remove_op(self.private['bob'], self.public['alice'], [hex_hash(add_b)])
        add_a = add_op(self.private['bob'], self.public['alice'], [hex_hash(remove_a1)])
        remove_a2 = remove_op(self.private['bob'], self.public['alice'], [hex_hash(add_a)])
        remove_b = remove_op(self.private['alice'], self.public['bob'], [hex_hash(add_a)])
        
        # Compute group membership  
        interpretation_results = interpret_ops({create, add_b, remove_b, remove_a1, add_a, remove_a2})
        members = interpretation_results['members']
        valid_messages = interpretation_results['valid_messages']

        self.assertEqual({self.friendly_name[member] for member in members}, {'alice'})
        self.assertEqual(valid_messages, set()) # no valid messages

    def test_post_then_remove(self):
      
        # Alice creates the group, then adds Bob. After Bob posts a valid message, Alice removes Bob 
        create = create_op(self.private['alice'])
        add_b = add_op(self.private['alice'], self.public['bob'], [hex_hash(create)])
        post_b = post_op(self.private['bob'], "This is Bob", [hex_hash(add_b)])
        rem_b = remove_op(self.private['alice'], self.public['bob'], [hex_hash(post_b)])

        # Compute group membership  + valid posts
        interpretation_results = interpret_ops({create, add_b, post_b, rem_b})
        members = interpretation_results['members']
        valid_messages = interpretation_results['valid_messages']

        self.assertEqual({self.friendly_name[member] for member in members}, {'alice'})
        self.assertEqual(valid_messages, {"This is Bob"})  # message still valid

    def test_remove_then_post(self):

        # Alice creates the group and adds Bob, then removes Bob. Afterwards, Bob posts a message
        create = create_op(self.private['alice'])
        add_b = add_op(self.private['alice'], self.public['bob'], [hex_hash(create)])
        rem_b = remove_op(self.private['alice'], self.public['bob'], [hex_hash(add_b)])
        post_b = post_op(self.private['bob'], "This is Bob", [hex_hash(rem_b)])

        # Compute group membership + valid posts
        interpretation_results = interpret_ops({create, add_b, rem_b, post_b})
        members = interpretation_results['members']
        valid_messages = interpretation_results['valid_messages']

        self.assertEqual({self.friendly_name[member] for member in members}, {'alice'})
        self.assertEqual(valid_messages, set())  # no valid messages
        
    def test_remove_add_then_post(self):
        
        # Alice creates the group and adds Bob, then removes Bob, then adds Bob again. After this, Bob posts a message
        create = create_op(self.private['alice'])
        add_b = add_op(self.private['alice'], self.public['bob'], [hex_hash(create)])
        rem_b = remove_op(self.private['alice'], self.public['bob'], [hex_hash(add_b)])
        add_b2 = add_op(self.private['alice'], self.public['bob'], [hex_hash(rem_b)])
        post_b = post_op(self.private['bob'], "This is Bob", [hex_hash(add_b2)])

        # Compute group membership  + valid posts
        interpretation_results = interpret_ops({create, add_b, rem_b, add_b2, post_b})
        members = interpretation_results['members']
        valid_messages = interpretation_results['valid_messages']

        self.assertEqual({self.friendly_name[member] for member in members}, {'alice', 'bob'})
        self.assertEqual(valid_messages, {"This is Bob"})  # message still valid
        
        
    def test_remove_post_then_add(self):
        
        # Alice creates the group and adds Bob, then removes Bob, then Bob posts a message. After this, Alice adds Bob again
        create = create_op(self.private['alice'])
        add_b = add_op(self.private['alice'], self.public['bob'], [hex_hash(create)])
        rem_b = remove_op(self.private['alice'], self.public['bob'], [hex_hash(add_b)])
        post_b = post_op(self.private['bob'], "This is Bob", [hex_hash(rem_b)])
        add_b2 = add_op(self.private['alice'], self.public['bob'], [hex_hash(post_b)])

        # Compute group membership  + valid posts
        interpretation_results = interpret_ops({create, add_b, rem_b, add_b2, post_b})
        members = interpretation_results['members']
        valid_messages = interpretation_results['valid_messages']

        self.assertEqual({self.friendly_name[member] for member in members}, {'alice', 'bob'})
        self.assertEqual(valid_messages, set())  # no valid messages

    def test_concurrent_remove_post(self):

        # Alice creates the group and adds Bob, then removes Bob, concurrently Bob posts a message
        create = create_op(self.private['alice'])
        add_b = add_op(self.private['alice'], self.public['bob'], [hex_hash(create)])
        rem_b = remove_op(self.private['alice'], self.public['bob'], [hex_hash(add_b)])
        post_b = post_op(self.private['bob'], "This is Bob", [hex_hash(add_b)])

        # Compute group membership  + valid posts
        interpretation_results = interpret_ops({create, add_b, rem_b, post_b})
        members = interpretation_results['members']
        valid_messages = interpretation_results['valid_messages']

        self.assertEqual({self.friendly_name[member] for member in members}, {'alice'})
        self.assertEqual(valid_messages, set())  # no valid messages       

    def test_create_twice(self):
        with self.assertRaises(Exception):
            create1 = create_op(self.private['alice'])
            create2 = create_op(self.private['bob'])
            interpret_ops({create1, create2})

    def test_no_create(self):
        with self.assertRaises(Exception):
            add_b = add_op(self.private['alice'], self.public['bob'])
            interpret_ops({ add_b })
    
 
if __name__ == '__main__':
    unittest.main()