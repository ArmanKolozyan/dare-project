import json
import secrets
import unittest
from hashlib import sha256
from nacl.signing import SigningKey, VerifyKey

# ADDED FOR EXERCISE 3
from enum import Enum
class PowerLevels(Enum):
    USER = 0
    MODERATOR = 50
    ADMINISTRATOR = 100
   
   
   
#group_creator_key = None
    


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
    signed_msg = signing_key.sign(json.dumps(message).encode('utf-8')) # json encoding
    return public_key + signed_msg # GEEFT GEWOON DE PUBLIC KEY MEE ZO, NICE

def verify_msg(signed_msg):
    """
    Takes a byte string of the form generated by ``sign_msg()``, checks the validity of the
    signature, and parses the JSON into a dictionary. The public key that signed the message is
    added to the dictionary under the key ``signed_by`` (as a hexadecimal string). Raises an
    exception if the signature is not valid.
    """
    public_key = VerifyKey(signed_msg[0:32]) # first 32 bytes are pubkey
    verified = json.loads(public_key.verify(signed_msg[32:])) # json decoding
    return {**verified, 'signed_by': signed_msg[0:32].hex()} 
    # ^ **verified refers to a dictionary unpacking operation that 
    # incorporates the key-value pairs from the verified dictionary into the new dictionary being returned

def create_op(signing_key):
    """Returns a group creation operation signed by ``signing_key``."""
    return sign_msg(signing_key, {'type': 'create', 'nonce': secrets.token_hex(16)}) # so that every group is unique

def add_op(signing_key, added_key, preds):
    """Returns an operation signed by ``signing_key``, which adds ``added_key`` to the group.
    ``preds`` is a list of hashes of immediate predecessor operations."""
    return sign_msg(signing_key, {'type': 'add', 'added_key': added_key, 'preds': preds})

def remove_op(signing_key, removed_key, preds):
    """Returns an operation signed by ``signing_key``, which removes ``removed_key`` from the group.
    ``preds`` is a list of hashes of immediate predecessor operations."""
    return sign_msg(signing_key, {'type': 'remove', 'removed_key': removed_key, 'preds': preds})

# ADDED FOR EXERCISE 2
def post_op(signing_key, message, preds):
    """Returns a signed application message (chat post) by ``signing_key``.
    ``message`` is the content of the chat message, and ``preds`` is a list of hashes of immediate predecessor operations.
    """
    return sign_msg(signing_key, {'type': 'post', 'message': message, 'preds': preds})

# ADDED FOR EXERCISE 3
def increase_pl_op(signing_key, power_level, increased_key, preds):
    return sign_msg(signing_key, {'type': 'increase_pl', 'power_level': power_level, 'increased_key' : increased_key, 'preds': preds})

def transitive_succs(successors, hash):
    """
    Takes ``successors``, a dictionary from operation hashes to sets of successor hashes, and a
    ``hash`` to start from. Returns a set of all hashes that are reachable from that starting point.
    """
    result = {hash}
    for succ in successors.get(hash, []):
        result.update(transitive_succs(successors, succ))
    return result

# ADDED FOR EXERCISE 2
def transitive_preds(predecessors, hash):
    """
    Takes `predecessors`, a dictionary from operation hashes to sets of predecessor hashes,
    and a `hash` to start from. Returns a set of all hashes that are predecessors of the starting point.
    """
    result = {hash}
    for pred in predecessors.get(hash, []):
        result.update(transitive_preds(predecessors, pred))
    return result

## ADDED TO MAKE THE MEMBERSHIP DETERMINATION CODE COMPLETE!
## NOW WE ALSO CHECK WHETHER THE ADDED USER OR THE ADDING USER IS CONCURRENTLY REMOVED!
def concurrent_removal(op, successors, ops_by_hash):
    """
    Checks if there is a concurrent 'remove' operation for the same added_key 
    that shares at least one predecessor with the given 'add' operation.
    
    Parameters:
    - op: The 'add' operation we are checking for concurrent removal.
    - successors: A dictionary where keys are operation hashes and values are sets of successor operations.
    - ops_by_hash: A dictionary where keys are operation hashes values are the corresponding operation data.
    """
    added_key = op['added_key']
    signed_by = op['signed_by']
    preds = op['preds']
    
    # finding all immediate successor operations of each predecessor
    immediate_succ = []
    for pred in preds:
        if pred in successors: # should always return true, but put here just in case
            immediate_succ.extend(ops_by_hash[succ_hash] for succ_hash in successors[pred])

    # 1. checking if any of the immediate successors is a 'remove' operation for the same added_key
    concurrent_user_removals = any(
        other_op['type'] == 'remove' and other_op['removed_key'] == added_key
        for other_op in immediate_succ
    )
    
    # 2. checking if any of the immediate successors is a 'remove' operation for the same signing key
    concurrent_adder_removals = any(
        other_op['type'] == 'remove' and other_op['removed_key'] == signed_by
        for other_op in immediate_succ
    )
    
    return (concurrent_user_removals or concurrent_adder_removals) 

## ADDED FOR EXERCISE 3
## Checks whether the power level increase is valid, i.e., the signer of the operation
## has sufficient power.
def is_valid_pl_increase(op, new_pl, preds, predecessors, successors, ops_by_hash):
    print("CHECKING")
    signer_key = op['signed_by']
    signer_pl = search_power_level(signer_key, preds, predecessors, successors, ops_by_hash)
    
    print(signer_pl)
    print(new_pl)
    
    return signer_pl >= new_pl    

## ADDED FOR EXERCISE 3
def search_power_level(key, preds, predecessors, successors, ops_by_hash):
    """
    Finds the most recent power_level of a user, starting from a given set of predecessors (preds).
    
    Parameters:
        key: The public key of the user.
        preds: The list of direct predecessor operations to start searching from.
        
    Returns:
        The most recent power level of the user if found, or -100 if no power level change is found.
    """
        
    # the creator of the group has Administrator rights, no checking needed
    # if key == group_creator_key:
    #     return PowerLevels.ADMINISTRATOR.value
    
    currents = list(preds)  # starting with the given predecessors
    # ^ we convert to a list to have order between predecessors
    
    power_level = PowerLevels.USER.value  # default power level if no updates are found

    print("VALIDARTION? ")

    while currents:
        current = currents.pop(0)  # getting the first item (most recent one to explore)
        
        current_op = ops_by_hash[current]
        
        print("VALIDARTION ")
        
        # checking if this operation is a 'power_level' change for the given user
        if current_op['type'] == 'increase_pl' and current_op['increased_key'] == key:
            
            # checking if valid
            if is_valid_pl_increase(current_op, current_op['power_level'], predecessors[current], predecessors, successors, ops_by_hash):
                
                if power_level < current_op['power_level']:
                    power_level = current_op['power_level']
                
                # checking if any concurrent increases of power level of the same user
                for pred in current_op['preds']:
                    immediate_succs = [(succ_hash, ops_by_hash[succ_hash]) for succ_hash in successors[pred]]
                    for (succ_hash, succ) in immediate_succs:
                        if succ['type'] == 'increase_pl' and succ['increased_key'] == key:
                            if is_valid_pl_increase(succ, succ['power_level'], predecessors[succ_hash], predecessors, successors, ops_by_hash):
                                # if so, we update to the LOWEST power level ## TODO: check met Jolien Swift, ik dacht gwn om safe te spelen
                                # OF GROOTSTE AUTORITIET
                                # OF HASH ALS TIGHT-BREAK
                                if succ['power_level'] < power_level:
                                    power_level = succ['power_level']
                
                break  # we exit early as we've found the most recent power level
        
        if current_op['type'] == 'create' and current_op['signed_by'] == key:
            power_level = PowerLevels.ADMINISTRATOR.value
            break
        
        # adding the transitivbe predecessors to be checked next
        currents.extend(current_op.get('preds', []))
    
    return power_level

## TODO:
# 1) comments
# 2) zie de argumenten preds en predecessors, kan je ze niet mergen naar 1???
# 3) kan je de 2 procedures niet mergen naar 1??
# 4) denk eens goed na over edge cases: wat als je king bent, en een mens probeert je een slaaf te maken, mag dat?? 
        # hmmm, is_valid_pl_increase is genoeg denk ik?
# 5) tests schrijven          
# 6) prints weghalen
def search_power_level_succ(key, nexts, preds, predecessors, successors, ops_by_hash):
        
    # the creator of the group has Administrator rights, no checking needed
    # if key == group_creator_key:
    #     return PowerLevels.ADMINISTRATOR.value
    
    currents = nexts  # starting with the given predecessors
    # ^ we convert to a list to have order between predecessors
    
    power_level = PowerLevels.USER.value  # default power level if no updates are found

    
    while currents:
        current = currents.pop(0)  # getting the first item (most recent one to explore)
        
        current_op = ops_by_hash[current]
        
        # checking if this operation is a 'power_level' change for the given user
        if current_op['type'] == 'increase_pl' and current_op['increased_key'] == key:
            print("UPDATED?")
            
            # checking if valid
            if is_valid_pl_increase(current_op, current_op['power_level'], predecessors[current], predecessors, successors, ops_by_hash):
                
                if power_level < current_op['power_level']:
                    print("UPDATED")
                    power_level = current_op['power_level']
                
                # checking if any concurrent increases of power level of the same user
                for pred in current_op['preds']:
                    immediate_succs = [ops_by_hash[succ_hash] for succ_hash in successors[pred]]
                    for succ in immediate_succs:
                        if succ['type'] == 'increase_pl' and succ['increased_key'] == key:
                            if is_valid_pl_increase(succ, succ['power_level'], preds, predecessors, successors, ops_by_hash):
                                # if so, we update to the LOWEST power level ## TODO: check met Jolien Swift, ik dacht gwn om safe te spelen
                                # OF GROOTSTE AUTORITIET
                                # OF HASH ALS TIGHT-BREAK
                                print("-----")
                                print(succ)
                                print("-----")
                                if succ['power_level'] < power_level:
                                    power_level = succ['power_level']
                                
        if current_op['type'] == 'create' and current_op['signed_by'] == key:
            power_level = PowerLevels.ADMINISTRATOR.value
            break
        
        # adding the transitivbe predecessors to be checked next      
        currents.extend(successors.get(current, []))
    
    return power_level        

def interpret_ops(ops):
    """
    Takes a set of access control and application operations and computes the currently authorised set of users # UPDATED FOR EXERCISE 2
    and valid messages. Throws an exception if something is not right.
    """
    
    # to change the value of a global variable inside a function, we need to refer to the variable by using the 'global' keyword
    # global group_creator_key 
    
    # Check all the signatures and parse all the JSON
    # creates a dictionary ops_by_hash, where the keys are the 
    # hashes of each operation, and the values are the verified 
    # operation data returned from verify_msg()
    ops_by_hash = {hex_hash(op): verify_msg(op) for op in ops}
    # list of the verified and parsed operations
    parsed_ops = ops_by_hash.values()

    ## SCHEMA VALIDATION
    # Every op must be one of the expected types
    if any(op['type'] not in {'create', 'add', 'remove', 'post', 'increase_pl'} for op in parsed_ops): # UPDATED FOR EXERCISE 2 and 3
        raise Exception('Every op must be either create, add, remove, post, or increase_pl')
    
    if any('added_key' not in op for op in parsed_ops if op['type'] == 'add'):
        raise Exception('Every add operation must have an added_key')
    
    if any('removed_key' not in op for op in parsed_ops if op['type'] == 'remove'):
        raise Exception('Every remove operation must have a removed_key')
    
    # ADDED FOR EXERCISE 2
    if any('message' not in op for op in parsed_ops if op['type'] == 'post'):
        raise Exception('Every post operation must have a message')
    

    # Hash graph integrity: every op except the initial creation must reference at least one
    # predecessor operation, and all predecessors must exist in the set
    if any(len(op['preds']) == 0 for op in parsed_ops if op['type'] != 'create'):
        raise Exception('Every non-create op must have at least one predecessor')
    if any(pred not in ops_by_hash # no dangling predecessors
           for op in parsed_ops if op['type'] != 'create'
           for pred in op['preds']):
        raise Exception('Every hash must resolve to another op in the set')

    # the set of successor hashes for each op 
    successors = {}
    
    # ADDED FOR EXERCISE 2
    # the set of predecessor hashes (in a dictionary) for each op
    predecessors = {}
    
    # filling in successors and predecessors
    for hash, op in ops_by_hash.items():
        for pred in op.get('preds', []):
            successors[pred] = successors.get(pred, set()) | {hash}
            predecessors[hash] = predecessors.get(hash, set()) | {pred} # ADDED FOR EXERCISE 2


    # Get the public key of the group creator
    create_ops = [(hash, op) for hash, op in ops_by_hash.items() if op['type'] == 'create']
    if len(create_ops) != 1:
        raise Exception('There must be exactly one create operation')
    

    # Only the group creator may sign add/remove ops (TODO: change this!)
    # if any(op['signed_by'] != create_op['signed_by'] for op in parsed_ops if op['type'] != 'post'):
    #    raise Exception('Only the group creator may sign add/remove operations')

    # Current group members are those who have been added, and not removed again by a remove
    # operation that is a transitive successor to the add operation.
    members = set()
    for hash, op in ops_by_hash.items():
        if op['type'] in {'create', 'add'}: # removal needs to be somewhere later (DAAROM DIE REVERSE NODIG!!)
            added_key = op['signed_by'] if op['type'] == 'create' else op['added_key']
            succs = [ops_by_hash[succ] for succ in transitive_succs(successors, hash)]
            # checking for future remove operations
            if not any(succ['type'] == 'remove' and succ['removed_key'] == added_key
                       for succ in succs):
                # ADDED: adding the member only if there is no concurrent removal operation of:
                # 1. the user
                # 2. the adder (the person that added this user)
                if not (op['type'] == 'add' and concurrent_removal(op, successors, ops_by_hash)):
                    
                    ## ADDED FOR EXERCISE 3: INITIALIZING POWER LEVELS
                    # if op['type'] == 'create':
                        #group_creator_key = op['signed_by']
                    members.add(added_key)
                    
        if  op['type'] == 'remove':
            remover = op['signed_by']
            to_remove = op['removed_key']
            power_level_removed = search_power_level(to_remove, op.get('preds', []), predecessors, successors, ops_by_hash)
            power_level_remover = search_power_level(remover, op.get('preds', []), predecessors, successors, ops_by_hash)
            if not power_level_removed < power_level_remover:
                raise Exception('User can only remove users with a power level < their own')            
       
    # ADDED FOR EXERCISE 2
    # If a user is removed, only the messages they posted while they were a member remain valid. 
    # Any messages they post after they are removed or concurrently with their removal, are discarded. 
    # We do this by signing application messages and making them a part of the hash graph, exactly like access control operations.            
    messages = set()
    for hash, op in ops_by_hash.items():            
        if op['type'] == 'post':
            signed_by = op['signed_by']
            
            # getting all predecessors of the post operation
            preds_by_hash = {pred : ops_by_hash[pred] for pred in transitive_preds(predecessors, hash)}
            
            # finding all remove operations for the author among the predecessors
            removals = [h for h, pred in preds_by_hash.items() if pred['type'] == 'remove' and pred['removed_key'] == signed_by]
        
            
            # flag to indicate if any removal of a user is followed by an add of that same user
            removal_without_add = False
            
            # checking each removal to see if it is followed by an 'add' operation for the same key
            for removal_hash in removals:
                
                # getting the successors of the removal operation
                rem_succ_ops = {succ : ops_by_hash[succ] for succ in transitive_succs(successors, removal_hash)}
                
                # if no 'add' operation exists in the successors, we mark removal_without_add as True
                if not any(rem_succ['type'] == 'add' 
                           and rem_succ['added_key'] == signed_by 
                           and hash in transitive_succs(successors, rem_succ_hash)  # the post must be a successor of the add!
                           for rem_succ_hash, rem_succ in rem_succ_ops.items()):
                    
                    removal_without_add = True
                    break  # no need to continue checking once we have found a valid removal without a subsequent add

            # if no removal (without a subsequent add) was found, we add the message to the valid messages
            if not removal_without_add:
                messages.add(op['message'])
    
    power_levels = [(member, (search_power_level_succ(member, [create_ops[0][0]], [], predecessors, successors, ops_by_hash))) for member in members]            
    return (members, messages, power_levels)


class TestAccessControlList(unittest.TestCase):
    # Generate keys for all the participants
    private = {name: SigningKey.generate() for name in {'alice', 'bob', 'carol', 'dave'}}
    public = {name: key.verify_key.encode().hex() for name, key in private.items()}
    friendly_name = {public_key: name for name, public_key in public.items()}
        
    

    def test_add_remove(self):
        # Make some example ops
        create = create_op(self.private['alice'])
        add_b = add_op(self.private['alice'], self.public['bob'], [hex_hash(create)]) # = [hex_hash(create)] => add happens after the create operation
        add_c = add_op(self.private['alice'], self.public['carol'], [hex_hash(create)]) # vorige ook create als vorige, dus parallel!
        rem_b = remove_op(self.private['alice'], self.public['bob'], [hex_hash(add_b), hex_hash(add_c)])

        # Compute group membership
        members, _, _ = interpret_ops({create, add_b, add_c, rem_b})
        self.assertEqual({self.friendly_name[member] for member in members}, {'alice', 'carol'})
        
    
    ## ADDED FOR CONCURRENT REMOVAL CHECK OF THE USER
    def test_concurrent_remove_user(self):
        """Test that adding a user concurrently with the removal of the user is invalid."""
        create = create_op(self.private['alice'])
        add_b = add_op(self.private['alice'], self.public['bob'], [hex_hash(create)])
        # adding Carol
        add_c = add_op(self.private['alice'], self.public['carol'], [hex_hash(add_b)])
        # concurrently removing Carol
        remove_c = remove_op(self.private['alice'], self.public['carol'], [hex_hash(add_b)])
        
        # checking if Carol is not a member
        members, _, _ = interpret_ops({create, add_b, add_c, remove_c})
        self.assertEqual({self.friendly_name[member] for member in members}, {'alice', 'bob'})
        
    
    ## ADDED FOR CONCURRENT REMOVAL CHECK OF THE ADDER (i.e., the person that added this user)
    def test_concurrent_remove_adder(self):
        """Test that adding a user concurrently with the removal of the person performing the add operation is invalid."""
        create = create_op(self.private['alice'])
        add_b = add_op(self.private['alice'], self.public['bob'], [hex_hash(create)])
        # Bob adds Carol
        add_c = add_op(self.private['bob'], self.public['carol'], [hex_hash(add_b)])
        # concurrently removing Bob (who added Carol)
        remove_c = remove_op(self.private['alice'], self.public['bob'], [hex_hash(add_b)])
        
        # checking if Carol is not a member
        members, _, _ = interpret_ops({create, add_b, add_c, remove_c})
        self.assertEqual({self.friendly_name[member] for member in members}, {'alice'})    
            
    
    # ADDED FOR EXERCISE 2
    def test_valid_post_before_removal(self):
        """Test that a post made before removal remains valid"""
        # creating group and adding Bob
        create = create_op(self.private['alice'])
        add_b = add_op(self.private['alice'], self.public['bob'], [hex_hash(create)])
        
        # Bob posts a valid message
        post_by_bob = post_op(self.private['bob'], "Hello, I am Bob", [hex_hash(add_b)])

        # Alice removes Bob after the post
        rem_b = remove_op(self.private['alice'], self.public['bob'], [hex_hash(add_b)])

        # computing group membership and valid posts
        members, valid_messages, _ = interpret_ops({create, add_b, post_by_bob, rem_b})

        # Bob should not be a member anymore, but his post should be valid
        self.assertEqual({self.friendly_name[member] for member in members}, {'alice'})
        self.assertEqual(valid_messages, {"Hello, I am Bob"})  # Bob's post should still be valid

    # ADDED FOR EXERCISE 2
    def test_invalid_post_after_removal(self):
        """Test that a post made after removal is invalid"""
        
        # creating group and adding Bob
        create = create_op(self.private['alice'])
        add_b = add_op(self.private['alice'], self.public['bob'], [hex_hash(create)])

        # Alice removes Bob
        rem_b = remove_op(self.private['alice'], self.public['bob'], [hex_hash(add_b)])

        # Bob tries to post after being removed
        post_by_bob_after_removal = post_op(self.private['bob'], "Hello, I am still here", [hex_hash(rem_b)])

        # computing group membership and valid posts
        members, valid_messages, _ = interpret_ops({create, add_b, rem_b, post_by_bob_after_removal})

        # Bob should not be a member, and his post after removal should be ignored
        self.assertEqual({self.friendly_name[member] for member in members}, {'alice'})
        self.assertEqual(valid_messages, set())  # no valid posts since Bob was removed
        
    # ADDED FOR EXERCISE 2
    def test_valid_post_after_removal_and_readding(self):
        """Test that a post made after removal, and after re-adding BEFORE the message, is valid"""
        
        # creating group and adding Bob
        create = create_op(self.private['alice'])
        add_b = add_op(self.private['alice'], self.public['bob'], [hex_hash(create)])

        # Alice removes Bob
        rem_b = remove_op(self.private['alice'], self.public['bob'], [hex_hash(add_b)])
        
        # Alice adds Bob again
        add_b_2 = add_op(self.private['alice'], self.public['bob'], [hex_hash(rem_b)])

        # Bob posts message
        post_by_bob = post_op(self.private['bob'], "Hello, I am still here", [hex_hash(add_b_2)])

        # computing group membership and valid posts
        members, valid_messages, _ = interpret_ops({create, add_b, rem_b, add_b_2, post_by_bob})

        # Bob should not be a member, and his post after removal should be ignored
        self.assertEqual({self.friendly_name[member] for member in members}, {'alice', 'bob'})
        self.assertEqual(valid_messages, {"Hello, I am still here"})  # the post is still valid
        
        
    # ADDED FOR EXERCISE 2
    def test_invalid_post_after_removal_and_before_readding(self):
        """Test that a post made after removal, and after re-adding AFTER the message, is invalid"""
        
        # creating group and adding Bob
        create = create_op(self.private['alice'])
        add_b = add_op(self.private['alice'], self.public['bob'], [hex_hash(create)])

        # Alice removes Bob
        rem_b = remove_op(self.private['alice'], self.public['bob'], [hex_hash(add_b)])

        # Bob posts message
        post_by_bob = post_op(self.private['bob'], "Hello, I am still here", [hex_hash(rem_b)])
        
        # Alice adds Bob again
        add_b_2 = add_op(self.private['alice'], self.public['bob'], [hex_hash(post_by_bob)])

        # computing group membership and valid posts
        members, valid_messages, _ = interpret_ops({create, add_b, rem_b, add_b_2, post_by_bob})

        # Bob should not be a member, and his post after removal should be ignored
        self.assertEqual({self.friendly_name[member] for member in members}, {'alice', 'bob'})
        self.assertEqual(valid_messages, set())  # the post is invalid  
        
    
    # ADDED FOR EXERCISE 3
    def test_valid_power_increase_administrator(self):
        """Test that increasing the power level of a user to ADMINISTRATOR is handled correctly."""
        
        # creating group and adding Bob
        create = create_op(self.private['alice'])
        add_b = add_op(self.private['alice'], self.public['bob'], [hex_hash(create)])
        
        # group creator increases Bob's power level to ADMINISTRATOR
        increase_pl = increase_pl_op(self.private['alice'], PowerLevels.ADMINISTRATOR.value, self.public['bob'], [hex_hash(add_b)])
        
        # computing group membership and power levels
        _, _, power_levels = interpret_ops({create, add_b, increase_pl})
        
        # asserting that the power levels are as expected for Alice and Bob (i.e., Bob should be ADMINISTRATOR)        
        self.assertEqual({(self.friendly_name[member], power_level) for (member, power_level) in power_levels}, 
                         {('alice', 100), ('bob', PowerLevels.ADMINISTRATOR.value)})
        
    # ADDED FOR EXERCISE 3
    def test_valid_power_increase_moderator(self):
        """Test that increasing the power level of a user to MODERATOR is handled correctly."""
        
        # creating group and adding Bob
        create = create_op(self.private['alice'])
        add_b = add_op(self.private['alice'], self.public['bob'], [hex_hash(create)])
        
        # group creator increases Bob's power level to MODERATOR
        increase_pl = increase_pl_op(self.private['alice'], PowerLevels.MODERATOR.value, self.public['bob'], [hex_hash(add_b)])
        
        # computing group membership and power levels
        _, _, power_levels = interpret_ops({create, add_b, increase_pl})
        
        # asserting that the power levels are as expected for Alice and Bob (i.e., Bob should be MODERATOR)        
        self.assertEqual({(self.friendly_name[member], power_level) for (member, power_level) in power_levels}, 
                         {('alice', PowerLevels.ADMINISTRATOR.value), ('bob', PowerLevels.MODERATOR.value)})
    
    # ADDED FOR EXERCISE 3
    def test_valid_power_increase_user(self):
        """Test that increasing the power level of a user to USER is handled correctly."""
        
        # creating group and adding Bob
        create = create_op(self.private['alice'])
        add_b = add_op(self.private['alice'], self.public['bob'], [hex_hash(create)])
        
        # group creator increases Bob's power level to USER
        increase_pl = increase_pl_op(self.private['alice'], PowerLevels.USER.value, self.public['bob'], [hex_hash(add_b)])
        
        # computing group membership and power levels
        _, _, power_levels = interpret_ops({create, add_b, increase_pl})
        
        # asserting that the power levels are as expected for Alice and Bob (i.e., Bob should be USER)        
        self.assertEqual({(self.friendly_name[member], power_level) for (member, power_level) in power_levels}, 
                         {('alice', PowerLevels.ADMINISTRATOR.value), ('bob', PowerLevels.USER.value)})   
    
    # ADDED FOR EXERCISE 3
    def test_valid_power_increase_default(self):
        """Test the default power levels when no power level increase operation is performed."""
        
        # creating group and adding Bob
        create = create_op(self.private['alice'])
        add_b = add_op(self.private['alice'], self.public['bob'], [hex_hash(create)])
        
        # computing group membership and power levels
        _, _, power_levels = interpret_ops({create, add_b})
        
        # asserting that the power levels are as expected for Alice and Bob (i.e., Bob should be USER)
        self.assertEqual({(self.friendly_name[member], power_level) for (member, power_level) in power_levels}, 
                         {('alice', PowerLevels.ADMINISTRATOR.value), ('bob', PowerLevels.USER.value)})  
    
    
    # ADDED FOR EXERCISE 3
    def test_valid_power_increase_3_people(self):
        """Test that power levels can be correctly increased when there are multiple members in the group."""   
        
        # creating group, adding Bob and Carol
        create = create_op(self.private['alice'])
        add_b = add_op(self.private['alice'], self.public['bob'], [hex_hash(create)])
        add_c = add_op(self.private['alice'], self.public['carol'], [hex_hash(add_b)])
        
        # group creator increases Bob's power level to MODERATOR
        increase_pl_Bob = increase_pl_op(self.private['alice'], PowerLevels.MODERATOR.value, self.public['bob'], [hex_hash(add_c)])
        
        # Bob increases Carol's power level to MODERATOR
        increase_pl_Carol = increase_pl_op(self.private['bob'], PowerLevels.MODERATOR.value, self.public['carol'], [hex_hash(increase_pl_Bob)])

        # computing group membership and power levels
        _, _, power_levels = interpret_ops({create, add_b, add_c, increase_pl_Bob, increase_pl_Carol})
        
        # asserting that the power levels are as expected for Alice and Bob (i.e., Bob should be USER)
        self.assertEqual({(self.friendly_name[member], power_level) for (member, power_level) in power_levels}, 
                         {('alice', PowerLevels.ADMINISTRATOR.value), ('bob', PowerLevels.MODERATOR.value), ('carol', PowerLevels.MODERATOR.value)})      
    
    
    # ADDED FOR EXERCISE 3
    def test_invalid_power_increase_higher_pl(self): 
        """Test that an invalid power level increase (higher than the signer's power level) is handled correctly."""  
        
        # creating group, adding Bob and Carol
        create = create_op(self.private['alice'])
        add_b = add_op(self.private['alice'], self.public['bob'], [hex_hash(create)])
        add_c = add_op(self.private['alice'], self.public['carol'], [hex_hash(add_b)])
        
        # group creator increases Bob's power level to MODERATOR
        increase_pl_Bob = increase_pl_op(self.private['alice'], PowerLevels.MODERATOR.value, self.public['bob'], [hex_hash(add_c)])
        
        # Bob tries to increase Carol's power level to ADMINISTRATOR (which is higher than its own power level)
        increase_pl_Carol = increase_pl_op(self.private['bob'], PowerLevels.ADMINISTRATOR.value, self.public['carol'], [hex_hash(increase_pl_Bob)])

        # computing group membership and power levels
        _, _, power_levels = interpret_ops({create, add_b, add_c, increase_pl_Bob, increase_pl_Carol})
        
        # asserting that the power levels are as expected for Alice and Bob (i.e., Bob should be USER)
        self.assertEqual({(self.friendly_name[member], power_level) for (member, power_level) in power_levels}, 
                         {('alice', PowerLevels.ADMINISTRATOR.value), ('bob', PowerLevels.MODERATOR.value), ('carol', PowerLevels.USER.value)})          
        
    def test_failure_1(self):
        with self.assertRaises(Exception):
            # adding without creating
            create = create_op(self.private['alice'])
            add_b = add_op(self.private['alice'], self.public('bob'), [])
    
    def test_failure_2(self):
        with self.assertRaises(Exception):
            # adding with wrong key
            create = create_op(self.private['alice'])
            add_b = add_op(self.private['arman'], self.public['bob'], [hex_hash(create)])      
                   
                   

if __name__ == '__main__':
    unittest.main()
