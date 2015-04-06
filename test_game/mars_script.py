import bge
import mathutils


def get_scene_by_name(name):
    scenes = bge.logic.getSceneList()   
    
    named_scene = None
         
    for scene in scenes:
        if scene.name == name:
            named_scene = scene
            
    return named_scene


def get_key(position):
    key = str(int(position[0])) + "$" + str(int(position[1])) 
    
    return key


def get_gun_dict():
    gun_dict = 	{	"pistol"	:	[	"bullet"	,	"flash"	,	2	,	False	,	-0.1	,	1	,	4	]	,
        "smg"	:	[	"bullet"	,	"flash"	,	5	,	False	,	0.0	,	1	,	5	]	,
        "laser"	:	[	"laser_bullet"	,	"laser"	,	1	,	True	,	0.1	,	5	,	20	]	,
        "flamer"	:	[	"flame"	,	"flame_effect"	,	9	,	False	,	0.1	,	1	,	6	]	,
        "rocket_launcher"	:	[	"rocket"	,	"big_flash"	,	1	,	False	,	0.0	,	10	,	100	]	,
        "reward"	:	[	None	,	None	,	1	,	False	,	0.0	,	200	,	0	]	,
        "no_weapon"	:	[	None	,	None	,	1	,	False	,	0.0	,	200	,	0	]	}

    return gun_dict


def key_triggered(key, tap=False):
    if tap:
        triggered = [1]
    else:
        triggered = [1, 2]
        
    if key in bge.logic.keyboard.events:    
        if bge.logic.keyboard.events[key] in triggered:
            return True
    
    return False


def elevator_control(own):
    run_left_pressed = key_triggered(bge.logic.globalDict['keys']["run_left"][0])
    run_right_pressed = key_triggered(bge.logic.globalDict['keys']["run_right"][0])
        
    walk_left_pressed = key_triggered(bge.logic.globalDict['keys']["walk_left"][0])   
    walk_right_pressed = key_triggered(bge.logic.globalDict['keys']["walk_right"][0])
    
    if run_left_pressed or walk_left_pressed:
        if own['facing'] != "left":
            own['turning'] = True
        
        own['facing'] = "left"
                        
    if run_right_pressed or walk_right_pressed:
        if own['facing'] != "right":
            own['turning'] = True
            
        own['facing'] = "right"
    

def jump_control(own):
    run_left_pressed = key_triggered(bge.logic.globalDict['keys']["run_left"][0])
    run_right_pressed = key_triggered(bge.logic.globalDict['keys']["run_right"][0])
    
    crouch_tapped = key_triggered(bge.logic.globalDict['keys']["crouch"][0],tap = True)  
    jump_tapped = key_triggered(bge.logic.globalDict['keys']["jump"][0],tap = True)  
    
    walk_left_pressed = key_triggered(bge.logic.globalDict['keys']["walk_left"][0])   
    walk_right_pressed = key_triggered(bge.logic.globalDict['keys']["walk_right"][0])
    
    if own['has_jetpack']:
        if run_left_pressed or walk_left_pressed:
            own['facing'] = "left"
                            
        if run_right_pressed or walk_right_pressed:
            own['facing'] = "right"
        
        if own['jet_fuel'] > 20:
            if jump_tapped:
                own['player_state'] = "JUMPING"         
                
    if crouch_tapped:
        own['player_state'] = "FALLING"              


def movement_check(own):
    run_left_pressed = key_triggered(bge.logic.globalDict['keys']["run_left"][0])
    run_right_pressed = key_triggered(bge.logic.globalDict['keys']["run_right"][0])
    
    crouch_tapped = key_triggered(bge.logic.globalDict['keys']["crouch"][0],tap = True)  
    jump_tapped = key_triggered(bge.logic.globalDict['keys']["jump"][0],tap = True)  
    
    walk_left_pressed = key_triggered(bge.logic.globalDict['keys']["walk_left"][0])   
    walk_right_pressed = key_triggered(bge.logic.globalDict['keys']["walk_right"][0])
        
    if run_left_pressed or walk_left_pressed:
        if own['facing'] != "left":
            own['turning'] = True
        
        own['facing'] = "left"
                        
    if run_right_pressed or walk_right_pressed:
        if own['facing'] != "right":
            own['turning'] = True
            
        own['facing'] = "right"
    
    if crouch_tapped:
        if not own['crouching'] and own['on_ground']:
            own['crouching'] = True
            own['running'] = False   
            own['walking'] = False
            
    elif jump_tapped:  
        if own['crouching']:
            own['crouching'] = False       
        elif own['on_ground'] and not own['jump_triggered']:
            if own['jet_fuel'] > 20.0 and not own['wall_blocked']:
                own['jump_triggered'] = True   
        
    elif not own['wall_blocked']:
                            
        if walk_left_pressed or walk_right_pressed:
            own['running'] = False   
            own['walking'] = True
        
        elif run_left_pressed or run_right_pressed:
            own['running'] = True   
            own['walking'] = False    
        else:
            own['running'] = False   
            own['walking'] = False      


def align_to_facing(own):
    turning_speed = 0.9
    
    if own['facing'] == "right":    
        facing_vector = mathutils.Vector([0.0, 1.0, 0.0])
    else:
        facing_vector = mathutils.Vector([0.0, -1.0, 0.0])     
        
    target_rotation = facing_vector.to_track_quat('Y', 'Z')
    
    agent_rotation = own['hook_object'].worldOrientation.to_quaternion()                                        
    slow_rotation = target_rotation.slerp(agent_rotation, turning_speed)
    own['hook_object'].worldOrientation = slow_rotation  


def add_jet_flame(own):
    scene = own.scene
    
    if own['jet_flame_pulse'] > 15:
        jet_sound = scene.addObject("jetpack_sound",own,0)
        jet_sound.setParent(own['skeleton_object'])
        own['main_control_object']['particles'].append(jet_sound)
        own['jet_flame_pulse'] = 0
        
    else:
        own['jet_flame_pulse'] += 1    
        
    jet_flame = scene.addObject("jetpack_particle",own,0)
    flame_hook = own['skeleton_object'].channels['jet_emitter']               
    flame_hook_matrix = flame_hook.pose_matrix.copy()            
    offset_matrix = own['skeleton_object'].worldTransform.copy()                        
    mat_out = (offset_matrix * flame_hook_matrix)
    
    jet_flame.worldTransform = mat_out
    
    own['main_control_object']['particles'].append(jet_flame)  
        

def apply_movement(own, cont):
    player_walk = cont.actuators['player_walk']
    
    drop_down = False            
    target_speed = 2.0  
    on_edge = False
        
    if own['turning']:
        own['movement'] = 0.0
        if own['turning_timer'] < 12.0:
            own['turning_timer'] += 1.0
        else:
            own['turning'] = False 
            own['turning_timer'] = 0.0       
    
    elif own['player_state'] == "WALKING":
        own['movement'] = target_speed * 1.0
    elif own['player_state'] == "RUNNING":
        own['movement'] = target_speed * 1.8
    elif own['player_state'] == "JUMPING":
        if own['jump_speed'] < 5.0:
            own['jump_speed'] += 0.1
        
        if own['has_jetpack']:
            add_jet_flame(own)
                                  
            own['movement'] = target_speed * 1.5
        else:
            own['movement'] = 4.0 
            
    elif own['player_state'] == "FALLING": 
        
        if own['on_right_edge']:  
            own['movement'] -= 0.2
            on_edge = True            
        elif own['on_left_edge']:              
            own['movement'] += 0.2
            on_edge = True            
        else:
            if abs(own['movement']) > 0.5:
                own['movement'] *= 0.99   
                 
    elif own['player_state'] == "CRASHING": 
        
        if own['on_right_edge']:  
            own['movement'] = -target_speed
            on_edge = True            
        elif own['on_left_edge']:              
            own['movement'] = target_speed
            on_edge = True
        else:
            if abs(own['movement']) > 0.5:
                own['movement'] *= 0.99
    
    elif own['player_state'] == "SCRABBLING":
        own['movement'] = 4.0                                             
    else:
        own['movement'] = 0.0
    
    if own['facing'] == "left" and own['movement'] != 0.0 and not on_edge:
        own['movement'] *= -1.0
                             
    y_setting = own['movement']
    
    if own['player_state'] == "ELEVATOR_RIDING":
        if not own['on_ground']:
            drop_down = True
        else:  
            z_setting = -4.0  
    
    elif own['player_state'] == "JUMPING": 
        
        z_setting = 7.0 - own['jump_speed']    
    
    elif own['player_state'] == "SCRABBLING":        
        z_setting = 6.0  
                    
    elif not own['on_ground']:   
        z_setting = -5.0
    else:
        own['jump_speed'] = 0.0
        z_setting = 0.0
    
    if not drop_down:
        player_walk.linV  = [ 0.0, y_setting, z_setting]
        cont.activate(player_walk)
    else:
        own.worldPosition.z -= 0.2    


def ground_check(own):
    local_position = own.worldPosition.copy()
    
    down_target = local_position.copy()
    down_target.z -= 1.1
    
    front_target = local_position.copy()
    front_target.z -= 1.0
    
    back_target = local_position.copy()
    back_target.z -= 1.0
        
    facing_target = local_position.copy()
    
    if own['facing'] == "right":
        facing_target.y += 1.1    
        front_target.y += 0.5  
        back_target.y -= 0.5      
    else:
        facing_target.y -= 1.1 
        front_target.y -= 0.5
        back_target.y += 0.5 
        
    wall_block_check = own.rayCast(facing_target, own, 0.0, "ground", 0, 1, 0)   
    down_check = own.rayCast(down_target, own, 0.0, "ground", 0, 1, 0)   
    front_check = own.rayCast(front_target, own, 0.0, "ground", 0, 1, 0)   
    back_check = own.rayCast(back_target, own, 0.0, "ground", 0, 1, 0)   
    
    own['on_right_edge'] = False
    own['on_left_edge'] = False
                    
    if down_check[0]:
        own['on_ground'] = True  
        if own['scrabbled_once']:
            own['scrabbled_once'] = False
              
    else:  
        own['on_ground'] = False
               
        if front_check[0]: 
            if own['facing'] == "right":   
                own['on_right_edge'] = True  
            else:
                own['on_left_edge'] = True             
            
        if back_check[0]:
            if own['facing'] == "left":   
                own['on_right_edge'] = True  
            else:
                own['on_left_edge'] = True 
    
    if wall_block_check[0]:
        own['wall_blocked'] = True
    else:
        own['wall_blocked'] = False     
    
    own['scrabbling'] = False
        
    can_scrabble =  not own['has_jetpack'] and not own['scrabbled_once']  
    scrabble_states = ["FALLING", "JUMPING"]
    
    if can_scrabble and own['player_state'] in scrabble_states:       
        if own['jet_fuel'] < 20:
            if own['facing'] == "left" and own['on_left_edge']:
                own['scrabbling'] = True
                own['scrabbled_once'] = True
            if own['facing'] == "right" and own['on_right_edge']:
                own['scrabbling'] = True             
                own['scrabbled_once'] = True

#    lines = [[local_position,front_target],[local_position,back_target],[local_position,down_target]]
#    color = [ 1.0, 0.0, 0.0]
#    
#    for line in lines:
#        
#        bge.render.drawLine(line[0], line[1], color)


def jumping_recharge(own):
    if own['has_jetpack']:
        own['max_jet_fuel'] = 200
    else:
        own['max_jet_fuel'] = 40   
    
    if own['jet_fuel'] > own['max_jet_fuel']:
        own['jet_fuel'] = own['max_jet_fuel']
    
    if own['on_ground']:                             
        if own['jet_fuel'] < own['max_jet_fuel']:
            own['jet_fuel'] += 3.0    


def handle_shooting(own, weapon_details):
    scene = own.scene
            
    if own['player_state'] == "CROUCHING" or own['player_state'] == "LANDING":
        emitter = own['bullet_adder_crouching']

    elif own['player_state'] == "JUMPING":
        emitter = own['bullet_adder_jumping']

    else:
        emitter = own['bullet_adder_standing']            
                           
    ### get bone_emitter 
    
    hand = own['skeleton_object'].channels['gun_hook']               
    hand_matrix = hand.pose_matrix.copy()            
    offset_matrix = own['skeleton_object'].worldTransform.copy()                        
    mat_out = (offset_matrix * hand_matrix)
        
    bullet = scene.addObject(weapon_details[0],own,0) 
    effect = scene.addObject(weapon_details[1],own,0)                          
    sound = scene.addObject(weapon_details[1] + "_sound",own,0)  
        
    if bullet.get("particle"):
        own['main_control_object']['particles'].append(bullet)

    if effect.get("particle"):
        own['main_control_object']['particles'].append(effect)

    if sound.get("particle"):
        own['main_control_object']['particles'].append(sound)  
    
    effect.worldTransform = mat_out             
    effect.localPosition.y += weapon_details[4]
    
    bullet.worldTransform = own['bullet_adder_standing'].worldTransform
    bullet.localPosition.y += weapon_details[4]
    
    own['weapon_ammo'] -= weapon_details[5]
    own['weapon_burst'] += 1 


def equipment_show(own):
    
    if own['has_armor']:
        own['armor_object'].visible = True
    else:
        own['armor_object'].visible = False
             
    if own['has_jetpack']:
        own['jetpack_object'].visible = True
    else:
        own['jetpack_object'].visible = False
 
    if own['weapon']:
        own['weapon_object'].visible = True        
        if own['weapon'] != own['current_weapon_mesh']:
            own['weapon_object'].replaceMesh(own['weapon'] + "_mesh")     
            own['current_weapon_mesh'] = own['weapon'] 
    else:
        own['weapon_object'].visible = False             


def check_damage(own):
    
    dead_states = ["DYING","CRASHING","CRASHED"] 
    
    if not own['player_state'] in dead_states:
        
        if own['player_state'] == "CROUCHING":
            if own['upper_hitbox'].get("can_hit"):
                del own['upper_hitbox']["can_hit"]
        else:
            if not own['upper_hitbox'].get("can_hit"):
                own['upper_hitbox']['can_hit'] = True
        
        hit_box_list = [own['upper_hitbox'],own['lower_hitbox']]
        
        for hitbox in hit_box_list:
        
            if hitbox['damage'] > 0.0:
                
                if own['has_armor']:                                    
                    own['health'] -= (hitbox['damage'] * 0.1)
                    own['armor'] -= hitbox['damage']
                else:
                    own['health'] -= hitbox['damage']  
            
                if own['armor'] < 0.0:
                    own['has_armor'] = False   
                    own['armor'] = 0.0  
                
                if own['health'] < 0.0:
                    own['dying'] = True
                    own['health'] = 0.0
                else:
                    own['being_hit'] = True
                    
                hitbox['damage'] = 0.0


def player(cont):
    own = cont.owner
    scene = own.scene
        
    if 'ini' not in own:
        player_dictionary = bge.logic.globalDict['player_dictionary']

        own['has_jetpack'] = player_dictionary['has_jetpack']
        own['has_armor'] = player_dictionary['has_armor']
        own['armor'] = player_dictionary['armor']
        own['health'] = player_dictionary['health']
        own['weapon'] = player_dictionary['weapon']
        own['weapon_ammo'] = player_dictionary['weapon_ammo']

        own['player_state'] = "IDLE"
        own['weapon_state'] = "IDLE"
                                
        own['jet_fuel'] = 200
        own['max_jet_fuel'] = 200  
        own['jump_timer'] = 0.0  
        own['jump_speed'] = 0.0
        own['jet_flame_pulse'] = 0
        
        own['max_armor'] = 100  
        own['max_health'] = 100
        
        own['movement'] = 0.0
                                
        own['turning'] = True
        own['turning_timer'] = 0.0
        own['wall_blocked'] = False
        own['jump_triggered'] = False
        own['on_ground'] = True
        own['on_right_edge'] = False
        own['on_left_edge'] = False
        own['scrabbling'] = False
        own['scrabble_count'] = 0
        own['scrabbled_once'] = False
        own['on_elevator'] = False
               
        own['facing'] = "right"
        own['crouching'] = False 
        own['running'] = False
        own['walking'] = False
        own['aiming'] = False
                
        own['current_weapon_mesh'] = "starting"
        own['weapon_cycle'] = 0
        own['weapon_burst'] = 0
        own['max_weapon_ammo'] = 100
                
        own['falling_count'] = 0
        own['damage_recycle'] = 0
        own['being_hit'] = False
        own['dying'] = False
        own['game_over_count'] = 0
        own['game_over'] = False
        own['restart'] = False
                             
        own.addDebugProperty("player_state")
        own.addDebugProperty("on_ground")
#        own.addDebugProperty("on_right_edge")
#        own.addDebugProperty("on_left_edge")
#        own.addDebugProperty("scrabbled_once")
                
        own['main_control_object'] = [ob for ob in scene.objects if ob.get("main_control")][0]
        own['hook_object'] = [ob for ob in own.children if ob.get("agent_hook")][0]
        own['skeleton_object'] = [ob for ob in own.childrenRecursive if ob.get("skeleton")][0]
                
        own['weapon_object'] = [ob for ob in own.childrenRecursive if ob.get("weapon_mesh")][0]
        own['armor_object'] = [ob for ob in own.childrenRecursive if ob.get("armor_mesh")][0]
        own['jetpack_object'] = [ob for ob in own.childrenRecursive if ob.get("back_pack_mesh")][0]
        own['bullet_adder_standing'] = [ob for ob in own.childrenRecursive if ob.get("bullet_adder") =="standing"][0]
        own['bullet_adder_jumping'] = [ob for ob in own.childrenRecursive if ob.get("bullet_adder") =="jumping"][0]
        own['bullet_adder_crouching'] = [ob for ob in own.childrenRecursive if ob.get("bullet_adder") =="crouching"][0]
        
        own['upper_hitbox'] = [ob for ob in own.childrenRecursive if ob.get("upper")][0]
        own['lower_hitbox'] = [ob for ob in own.childrenRecursive if ob.get("lower")][0]

        # Register particles
        main_control = own['main_control_object']
        for ob in own.childrenRecursive:
            if ob.get("particle"):
                main_control['particles'].append(ob)

        # Add HUD
        hud_scene = get_scene_by_name("hud_scene")
        if not hud_scene:
            bge.logic.addScene('hud_scene')

        # Move to spawn
        own.worldTransform = own['main_control_object'].worldTransform.copy()
        
        own['ini'] = True  
           
    else:
        
        shoot_tapped = key_triggered(bge.logic.globalDict['keys']["shoot"][0],tap = True) 
                
        ground_check(own)
        apply_movement(own,cont)        
        jumping_recharge(own)
        equipment_show(own)
        check_damage(own)
                                                          
        if own['player_state'] == "IDLE":
            
            if own['dying']:
                if own['on_ground']:
                    own['player_state'] = "DYING"
                else:
                    own['player_state'] = "CRASHING"  
            
            elif own['on_elevator']:
                own['player_state'] = "ELEVATOR_RIDING"  
            
            elif not own['on_ground']:
                own["player_state"] = "FALLING"
            else:                            
                movement_check(own)            
                align_to_facing(own)   
                
                if own['weapon']:
                    default_action = "player_default"
                else:
                    default_action = "player_unarmed"
                
                own['skeleton_object'].playAction(default_action, 0, 120, priority=1, blendin=12,
                                                  play_mode=bge.logic.KX_ACTION_MODE_LOOP)
                          
                if own['walking']:
                    own["player_state"] = "WALKING"
                if own['running']:
                    own["player_state"] = "RUNNING"
                if own['crouching']:
                    own["player_state"] = "CROUCHING"
                if own['jump_triggered']:
                    own["player_state"] = "START_JUMP"
                
        elif own['player_state'] == "WALKING":
            
            if own['dying']:
                if own['on_ground']:
                    own['player_state'] = "DYING"
                else:
                    own['player_state'] = "CRASHING"  
            
            elif not own['on_ground']:
                own["player_state"] = "FALLING"
            elif own['wall_blocked']: 
                own["player_state"] = "IDLE" 
                
            else:                    
                movement_check(own)            
                align_to_facing(own)  
                own['skeleton_object'].playAction("player_walk", 0, 21, priority=1, blendin=12,
                                                  play_mode=bge.logic.KX_ACTION_MODE_LOOP)
                                                        
                if not own['walking']:
                    own["player_state"] = "IDLE"        
                if own['running']:
                    own["player_state"] = "RUNNING"
                if own['crouching']:
                    own["player_state"] = "CROUCHING"
                if own['jump_triggered']:
                    own["player_state"] = "START_JUMP"
                
        elif own['player_state'] == "RUNNING":
            if own['dying']:
                if own['on_ground']:
                    own['player_state'] = "DYING"
                else:
                    own['player_state'] = "CRASHING"  
            
            elif not own['on_ground']:
                own["player_state"] = "FALLING"
                
            elif own['wall_blocked']: 
                own["player_state"] = "IDLE" 
            else:   
                
                movement_check(own)            
                align_to_facing(own)  
                own['skeleton_object'].playAction("player_run", 0, 21, priority=1, blendin=12, play_mode=bge.logic.KX_ACTION_MODE_LOOP)
                                  
                if own['walking']:
                    own["player_state"] = "WALKING"        
                if not own['running']:
                    own["player_state"] = "IDLE"
                if own['crouching']:                    
                    own["player_state"] = "CROUCHING"
                if own['jump_triggered']:
                    own["player_state"] = "START_JUMP"  
        
        elif own['player_state'] == "CROUCHING":
            
            if own['dying']:
                if own['on_ground']:
                    own['player_state'] = "DYING"
                else:
                    own['player_state'] = "CRASHING"  
            
            elif not own['on_ground']:
                own["player_state"] = "FALLING"
            else:                   
                movement_check(own)            
                align_to_facing(own)  
                own['skeleton_object'].playAction("player_crouch", 0, 120, priority=1, blendin=12, play_mode=bge.logic.KX_ACTION_MODE_LOOP)
                                  
                if own['walking']:
                    own["player_state"] = "WALKING"   
                    own['crouching'] = False     
                if own['running']:
                    own["player_state"] = "RUNNING"
                    own['crouching'] = False
                if not own['crouching']:
                    own["player_state"] = "IDLE"
        
        elif own['player_state'] == "START_JUMP":
            align_to_facing(own)  
            
            if own['dying']:
                if own['on_ground']:
                    own['player_state'] = "DYING"
                else:
                    own['player_state'] = "CRASHING"  
            
            elif not own['on_ground']:
                own["player_state"] = "FALLING"
                
            else:                                                    
                own['skeleton_object'].playAction("player_crouch", 0, 120, priority=1, blendin=4, play_mode=bge.logic.KX_ACTION_MODE_LOOP)
                                  
                own['jump_triggered'] = False
                
                if own['jump_timer'] < 15.0:
                    own['jump_timer'] += 1.0
                else:
                    own['player_state'] = "JUMPING"
                    own['jump_timer'] = 0.0   
                                              
        elif own['player_state'] == "JUMPING":
            if own['dying']:
                if own['on_ground']:
                    own['player_state'] = "DYING"
                else:
                    own['player_state'] = "CRASHING"  
            
            elif own['scrabbling']:
                own['player_state'] = "SCRABBLING"
                
            else:                        
                jump_control(own)           
                align_to_facing(own)  
                               
                own['skeleton_object'].playAction("player_jump", 0, 21, priority=1, blendin=12, play_mode=bge.logic.KX_ACTION_MODE_LOOP)
                                                          
                if own['jet_fuel'] > 0.0:
                    own['jet_fuel'] -= 1.0
                else:
                    own['player_state'] = "FALLING"      
        
        elif own['player_state'] == "SCRABBLING":
            align_to_facing(own) 
            
            if own['dying']:
                if own['on_ground']:
                    own['player_state'] = "DYING"
                else:
                    own['player_state'] = "CRASHING"
            
            else:            
                own['skeleton_object'].playAction("player_no_jetpack", 0, 21, priority=1, blendin=2, play_mode=bge.logic.KX_ACTION_MODE_LOOP)
                
                if own['scrabble_count'] > 10:
                    own['player_state'] = "FALLING"
                    own['scrabble_count'] = 0
                else:
                    own['scrabble_count'] += 1   

        elif own['player_state'] == "FALLING":
            if own['dying']:
                own['player_state'] = "CRASHING"  
            
            elif own['scrabbling']:
                own['player_state'] = "SCRABBLING"
                                
            else: 
                
                if own['has_jetpack']:
                    max_fall = 360
                else:
                    max_fall = 100
                   
                if own['falling_count'] > max_fall:
                    own['player_state'] = "CRASHING" 
                else:
                    if not own['has_jetpack'] or own['jet_fuel'] < 1.0:
                        own['falling_count'] += 1        
                             
                    jump_control(own)                         
                    align_to_facing(own)  
                    own['skeleton_object'].playAction("player_falling", 0, 120, priority=1, blendin=12, play_mode=bge.logic.KX_ACTION_MODE_LOOP)
                    
                    if own['facing'] == "left" and own['on_left_edge']:
                        own['falling_count'] = 0    
                        
                    if own['facing'] == "right" and own['on_right_edge']:
                        own['falling_count'] = 0
                                                              
                    if own['on_ground']:  
                        own['falling_count'] = 0           
                        own['player_state'] = "LANDING"                 
            
        elif own['player_state'] == "LANDING":
            if own['dying']:
                own['player_state'] = "DYING"  
                
            else:                                
                align_to_facing(own)               
                own['skeleton_object'].playAction("player_crouch", 0, 120, priority=1, blendin=12, play_mode=bge.logic.KX_ACTION_MODE_LOOP)
                                                          
                if own['on_ground']:  
                    if own['jump_timer'] < 30.0:
                        own['jump_timer'] += 1.0
                    else:   
                        own['jump_timer'] = 0.0                                  
                        own['player_state'] = "IDLE"           
                else:
                    own['player_state'] = "FALLING"  
        
        elif own['player_state'] == "DYING":
            if own['game_over_count'] > 160:
                own['restart'] = True
            else:
                own['game_over_count'] += 1
                if own['dying']:                    
                    own['skeleton_object'].playAction("player_die", 0, 50, priority=0, blendin=12, play_mode=bge.logic.KX_ACTION_MODE_PLAY)
                    own['dying'] = False
                    own['game_over'] = True
        
        elif own['player_state'] == "CRASHING":
            if own['on_ground']:
                own['dying'] = True
                own['health'] = 0                
                own['player_state'] = "CRASHED"

            else:
                own['skeleton_object'].playAction("player_crashing", 0, 50, priority=1, blendin=12, play_mode=bge.logic.KX_ACTION_MODE_LOOP)
        
        elif own['player_state'] == "CRASHED":
            if own['game_over_count'] > 160:
                own['restart'] = True                
            else:
                own['game_over_count'] += 1
                
                if own['dying']:
                    own['skeleton_object'].playAction("player_crashed", 0, 21, priority=0, blendin=12, play_mode=bge.logic.KX_ACTION_MODE_PLAY)
                    own['dying'] = False
                    blood = scene.addObject("blood_hit",own,0)
                    hit_sound = scene.addObject("plasma_hit_sound",own,60) 
                    own['main_control_object']['particles'].append(blood)                    
                                        
                    own['game_over'] = True                  
         
        elif own['player_state'] == "ELEVATOR_RIDING":
            elevator_control(own)
            align_to_facing(own)    
            
            if own['dying']:
                own['player_state'] = "CRASHING"
            
            elif not own['on_elevator']:
                own['player_state'] = "IDLE" 
            else:                
                if own['weapon']:
                    default_action = "player_default"
                else:
                    default_action = "player_unarmed"
                
                own['skeleton_object'].playAction(default_action, 0, 120, priority=1, blendin=12, play_mode=bge.logic.KX_ACTION_MODE_LOOP)
                               
                
        ### weapon states
               
        if own['weapon']:
            weapon_key =  own['weapon']
        else:
            weapon_key = "no_weapon"       
                
        weapon_details = get_gun_dict()[weapon_key]
        
        def shooting_valid(own):
            
            if own['weapon']:
                weapon_key =  own['weapon']
            else:
                weapon_key = "no_weapon"       
                    
            weapon_details = get_gun_dict()[weapon_key]
            
            dead_states = ["DYING","CRASHING","CRASHED"]
            if own['weapon']:
                if own['player_state'] not in dead_states:
                    if not own['wall_blocked']:
                        if not own['weapon_state'] == "DAMAGED":
                            if own['turning_timer'] < 0.1: 
                                if weapon_details[0]:
                                    if own['weapon_ammo'] > weapon_details[5]: 
                                        return True
            
            return False   
        
                     
        if own['weapon_state'] == "IDLE": 
            
            if own['being_hit']:
                dead_states = ["DYING","CRASHING","CRASHED"] 
                if own['player_state'] not in dead_states:
                    own['weapon_state'] = "DAMAGED"
                else:
                    own['being_hit'] = False  
                
            else:                                
                own['skeleton_object'].playAction("player_dont_shoot",0,21,  layer=1, blendin=12, priority=1, play_mode=bge.logic.KX_ACTION_MODE_LOOP)          
                             
                if shooting_valid(own):
                    shoot_tapped = key_triggered(bge.logic.globalDict['keys']["shoot"][0],tap = True)
                    
                    if shoot_tapped: 
                        if own['weapon_ammo'] > weapon_details[5]:
                            own['weapon_state'] = "AIMING" 
                            own['weapon_cycle'] = 0
                            own['weapon_burst'] = 0
        
        elif own['weapon_state'] == "DAMAGED":
            dead_states = ["DYING","CRASHING","CRASHED"]
            
            if own['player_state'] in dead_states:
                own['damage_recycle'] = 0
                own['being_hit'] = False
                own['weapon_state'] = "IDLE"    
            
            elif own['being_hit']:
                own['skeleton_object'].playAction("player_hit",0,21,  layer=1, blendin=12, priority=1, play_mode=bge.logic.KX_ACTION_MODE_LOOP)          
                
                own['damage_recycle'] = 0
                own['being_hit'] = False
            
            else:
                if own['damage_recycle'] > 40:
                    own['weapon_state'] = "IDLE"
                    own['damage_recycle'] = 0
                else:
                    own['damage_recycle'] += 1
                                                                                
        elif own['weapon_state'] == "AIMING":
                        
            if shooting_valid(own):                
                
                own['skeleton_object'].playAction("player_shoot_1",0,21,  layer=1, blendin=4, priority=1, play_mode=bge.logic.KX_ACTION_MODE_LOOP)          
                           
                if own['weapon_cycle'] > 25:
                    own['weapon_state'] = "SHOOTING"
                    own['weapon_cycle'] = 0
                else:
                    own['weapon_cycle'] += 1     
            
            else:
                own['weapon_state'] = "IDLE"
                own['weapon_cycle'] = 0
                own['weapon_burst'] = 0
                
        elif own['weapon_state'] == "SHOOTING":  
            
            if shooting_valid(own):
                
                own['skeleton_object'].playAction("player_shoot_1",0,21,  layer=1, blendin=12, priority=1, play_mode=bge.logic.KX_ACTION_MODE_LOOP)          
                
                handle_shooting(own,weapon_details)
                            
                own['weapon_state'] = "RECYCLE"
                
            else:
                own['weapon_state'] = "IDLE"
                own['weapon_cycle'] = 0
                own['weapon_burst'] = 0       
            
        elif own['weapon_state'] == "RECYCLE":
            
            own['skeleton_object'].playAction("player_shoot_1",0,21,  layer=1, blendin=12, priority=1, play_mode=bge.logic.KX_ACTION_MODE_LOOP)          
                        
            if shooting_valid(own) and own['weapon_burst'] < weapon_details[2]: 
                
                if own['weapon'] == "flamer":
                    cycle_time = 0
                else:
                    cycle_time = 3 
                
                if own['weapon_cycle'] > cycle_time:
                    own['weapon_state'] = "SHOOTING"
                    own['weapon_cycle'] = 0
                else:
                    own['weapon_cycle'] += 1        
            else:
                own['weapon_state'] = "IDLE"
                own['weapon_cycle'] = 0
                own['weapon_burst'] = 0                    


def slow_parent(own):
    relations = [[own,own['player_ob']],[own['back_drop'],own]]
    
    for relation in relations:
        
        start = relation[1].worldPosition.copy()
        end = relation[0].worldPosition.copy()
                
        target_vector = end-start
        
        if target_vector.length >= 0.032:
        
            target_vector.length *= 0.02
            
            new_position = end - target_vector
            new_position.x = relation[0].worldPosition.copy().x
            
            relation[0].worldPosition = new_position


### keep this for later
def get_nearet_target(own,property):
    scene = own.scene
    
    target = None
    
    object_list = [ob for ob in scene.objects if ob.get(property)]
    if object_list:
        object_list.sort(key=own.getDistanceTo)
        target = object_list[0]
    
    return target


def particle_collision(particle):
    
    y_axis = mathutils.Vector([0.0, 1.0, 0.0])
    local_y_vector = particle.getAxisVect(y_axis) 
    local_y_vector.length = particle.get('y_move',0.3)
    
    particle_position = particle.worldPosition.copy()    
    end_position = particle_position + local_y_vector
    
    hit_ray = particle.rayCast(end_position, particle, 0.0, "can_hit", 0, 1, 0)
    
    if hit_ray[0]:
        return (True,hit_ray[0],hit_ray[1])
    else:
        return (False,21.0)


def laser_ray(particle):
    y_axis = mathutils.Vector([0.0, 1.0, 0.0])
    local_y_vector = particle.getAxisVect(y_axis) 
    local_y_vector.length = 21.0
    
    particle_position = particle.worldPosition.copy()    
    end_position = particle_position + local_y_vector
    
    hit_ray = particle.rayCast(end_position, particle, 0.0, "can_hit", 0, 1, 0)
    
    if hit_ray[0]:
        return (True,hit_ray[0],hit_ray[1])
    else:
        return (False,21.0)
 
 
def player_tracking(own, particle):
    
    scene = own.scene
    turning_speed = 0.9
    
    if not "player_object" in particle:
        player = own.get('player_ob')
        if player:
            particle['player_object'] = player
        else:
            particle['player_object'] = None
    else:       
        y_axis = mathutils.Vector([0.0, 1.0, 0.0])
        local_y_vector = particle.getAxisVect(y_axis) 
        local_y_vector.length = 0.1
          
        if particle['player_object']:
                                             
            target_vector = particle['player_object'].worldPosition.copy() - particle.worldPosition.copy()
            angle = local_y_vector.angle(target_vector)
            
            if angle > 1.0:
                particle['player_object'] = None
                particle.worldPosition += local_y_vector
            else:
                target_rotation = target_vector.to_track_quat('Y', 'Z')
                particle_rotation = particle.worldOrientation.to_quaternion()                                        
                slow_rotation = target_rotation.slerp(particle_rotation,turning_speed)                    
                particle.worldOrientation = slow_rotation 
                
                local_y_vector = particle.getAxisVect(y_axis)
                local_y_vector.length = 0.1
                particle.worldPosition += local_y_vector 
        
        else:
            particle.worldPosition += local_y_vector   
        
        end_position = particle.worldPosition.copy() + local_y_vector 
            
        hit_ray = particle.rayCast(end_position, particle, 0.0, "can_hit", 0, 1, 0)
        
        if hit_ray[0]:
            return (True,hit_ray[0],hit_ray[1])
        else:
            return (False,21.0) 
    
    return (False,21.0)      


def hunter_collision(own,particle):
    
    speed = particle.get("speed",0.06)
    
    if "player_object" not in particle:
    
        player = own.get('player_ob')
        
        if player:          
            target_vector = player.worldPosition.copy() - particle.worldPosition.copy()
            if target_vector.length < 6.0:
                
                non_detection_states = ["IDLE","WALKING","CROUCHING"]
                
                if player['player_state'] not in non_detection_states: 
                    
                    particle['player_object'] = player
                    y_axis = mathutils.Vector([0.0, 1.0, 0.0])
                    initial_vector = particle.getAxisVect(y_axis) 
                    initial_vector.length = speed
                    
                    particle['initial_vector'] = initial_vector
                                
    else:
        
        target_vector = particle['player_object'].worldPosition.copy() - particle.worldPosition.copy() 
        target_vector.length = speed
        
        ray_vector = target_vector.copy()
        ray_vector.length = 0.2 
        
        end_position = particle.worldPosition.copy() + ray_vector
                        
        movement_vector =  target_vector.lerp(particle['initial_vector'],0.2)                    
        particle.worldPosition += movement_vector       
                  
        hit_ray = particle.rayCast(end_position, particle, 0.0, "can_hit", 0, 1, 0)
        
        if hit_ray[0]:
            return (True,hit_ray[0],hit_ray[1])
        else:
            return (False,21.0) 
    
    return (False,21.0)         


def particle_control(own):
    scene = own.scene
    
    next_generation = []
    light_sources = []
        
    for particle in own['particles']:
        save_particle = True
        
        if not particle.invalid:
                            
            if particle.get('life_time'):
                if particle['life_time'] > 1:
                    particle['life_time'] -= 1
                else:
                    save_particle = False
            
            if particle.get("shadow"):
                start_point = particle.parent.worldPosition.copy()
                down_target = particle.worldPosition.copy()
                down_target.z -= 100.0
                
                shadow_ray = own.rayCast(down_target, start_point, 0.0, "ground", 0, 1, 0)        
                
                if shadow_ray[0]:
                    particle.worldPosition.z = shadow_ray[1].z  
                    particle.visible = True   
                else:
                    particle.visible = False        
    
            if particle.get("grow"):
                particle.localScale *= 1.3
                
            if particle.get("fade"):
                particle.color *= 0.7   
            
            if particle.get("long_fade"):
                particle.color *= 0.9
                particle.localScale *= 1.05
                        
            if particle.get("animation"):
                if not particle.isPlayingAction():
                    particle.playAction(particle.get("ani_name","hunter_drone_glow"), 0, particle.get("ani_length",4), play_mode=bge.logic.KX_ACTION_MODE_PLAY)
                                            
            if particle.get("player_tracking") or particle.get("hunter"): 
                
                speed = particle.get("y_move",0.1)
                
                if particle.get("player_tracking"):                
                    collision = player_tracking(own,particle)
                else:
                    collision = hunter_collision(own,particle)      
                                
                if collision[0]:
                    if collision[1].get("player_hit"):
                        collision[1]['damage'] = particle.get("damage",15)
                        collision[1]['being_hit'] = True 
                    
                    collision_hit = scene.addObject("collision_hit",particle,0)
                    collision_hit.localScale = [1.0,1.0,1.0]
                    collision_hit_sound = scene.addObject("collision_hit_sound",particle,60)
                    
                    if particle.get("explode"):
                        for i in range(6):
                            trash = "trash_" + str(i)
                            trash_object = scene.addObject(trash,particle,0)
                            
                            y_axis = mathutils.Vector([0.0, 1.0, 0.0])
                            local_y_vector = particle.getAxisVect(y_axis) 
                            local_y_vector.length = speed * 0.5
                            
                            trash_object['initial_vector'] = local_y_vector
                            own['particles'].append(trash_object)
                                                
                    next_generation.append(collision_hit) 
                    save_particle = False  
                
                
            if particle.get("y_move"):
                particle.applyMovement([0.0,particle['y_move'],0.0],True) 
                
                collision = particle_collision(particle)
                if collision[0]:
                    if collision[1].get("enemy"):
                        if not collision[1].get("has_shield"):
                            collision[1]['damage'] = particle.get("damage",3)
                            collision[1]['being_hit'] = True 
                    
                    collision_hit = scene.addObject("collision_hit",particle,0)
                    collision_hit.localScale = [1.0,1.0,1.0]
                    collision_hit_sound = scene.addObject("collision_hit_sound",particle,60)
                    
                    if particle.get("explode"):
                        for i in range(6):
                            trash = "trash_" + str(i)
                            trash_object = scene.addObject(trash,particle,0)
                            
                            y_axis = mathutils.Vector([0.0, 1.0, 0.0])
                            local_y_vector = particle.getAxisVect(y_axis) 
                            local_y_vector.length = particle['y_move'] * 0.5
                            
                            trash_object['initial_vector'] = local_y_vector
                            own['particles'].append(trash_object)
                                            
                    next_generation.append(collision_hit) 
                    save_particle = False  
            
            if particle.get("plasma_bullet"):
                particle.applyMovement([0.0,0.25,0.0],True) 
                
                collision = particle_collision(particle)
                if collision[0]:
                    if collision[1].get("player_hit"):
                        collision[1]['damage'] = particle['damage']
                        collision[1]['being_hit'] = True 
                    
                    collision_hit = scene.addObject("plasma_hit",particle,0)
                    collision_hit.localScale = [1.0,1.0,1.0]
                    collision_hit_sound = scene.addObject("plasma_hit_sound",particle,60)
                    
                    next_generation.append(collision_hit) 
                    save_particle = False  
                        
            if particle.get("bullet_ray"):
                collision = laser_ray(particle)
                if collision[0]:
                    if collision[1].get("enemy"):
                        if not collision[1].get("has_shield"):
                            collision[1]['damage'] = 4
                            collision[1]['being_hit'] = True  
                    
                    collision_hit = scene.addObject("sparks_hit",particle,0)
                    collision_hit.localScale = [1.0,1.0,1.0]
                    collision_hit.worldPosition = collision[2]
                    
                    collision_hit_sound = scene.addObject("sparks_sound",particle,60)
                    
                    next_generation.append(collision_hit)  
                                    
                save_particle = False 
            
            if particle.get("trash"):
                if "calculated" not in particle:
                    particle['movement'] = mathutils.Vector([bge.logic.getRandomFloat() *0.1 for i in range(3)])
                    
                    if particle.get("initial_vector"):
                                                
                        particle['movement'] -= particle['initial_vector']    
                                        
                    particle["calculated"] = True
                    
                else:
                    particle['movement'].z -= 0.005
                    particle.worldPosition += particle['movement'] 
            
            if particle.get("laser_ray"):
                if "calculated" not in particle:
                    
                    collision = laser_ray(particle)  
                    
                    if collision[0]:
                        if collision[1].get("enemy"):
                            collision[1]['damage'] = 12
                            collision[1]['being_hit'] = True   
                        
                        distance = particle.getDistanceTo(collision[2])
                        particle.localScale[1] = distance
                                                                
                        collision_hit = scene.addObject("laser_hit",particle,0)
                        collision_hit.localScale = [1.0,1.0,1.0]
                        collision_hit.worldPosition = collision[2]
                        
                        collision_hit_sound = scene.addObject("collision_hit_sound",particle,60)
                        
                        next_generation.append(collision_hit)  
                                                          
                    else:
                         particle.localScale[1] = collision[1]
                         
                    particle['calculated'] = True
                                                                     
            if particle.get("light_hook"):
                light_sources.append(particle)
            
            if particle.get("add_trail"): 
                flame_trail = scene.addObject("flame_trail",particle,0)
                next_generation.append(flame_trail)
                
            if save_particle:
                next_generation.append(particle)  
            else:
                particle.endObject()
            
    own['particles'] = next_generation

    player_ob = get_local_player(scene)
    light_sources.sort(key=player_ob.getDistanceTo)
    
    number_of_light_sources = len(light_sources)        
    number_of_lights = len(own['lights'])
        
    color_dict = { "red": [1.0,0.15,0.0],
    "green": [0.0,1.0,0.15],
    "blue": [0.15,0.3,1.0],
    "white":[0.9,0.9,1.0],
    "purple":[0.65,0.0,1.0]}
        
    for i in range(number_of_lights):
        light = own['lights'][i]
        
        if i < number_of_light_sources:
            light_souce = light_sources[i]
            light.worldPosition = light_souce.worldPosition.copy()
            light.worldPosition.x += 3.0
            if light_souce.get("light_color","null") in color_dict:
                light.color = color_dict[light_souce["light_color"]]  
                light.energy = 2.0  
            else:
                light.color = [1.0,1.0,1.0]
                light.energy = 1.0
        else:
            light.energy = 0.0
                             

def pickup_setup(own):
    scene = own.scene
    weapon_dictionary = get_gun_dict()
    
    for pickup in scene.objects:
        if pickup.get("item_pickup"):
            
            if pickup.worldPosition.copy().to_tuple() in bge.logic.globalDict['cleared_up']:
                pickup.endObject()
            else:
                
                try:
                    if pickup['pickup_type'] == "reward" or pickup['pickup_type'] =="ammo" or pickup['pickup_type'] == "check_point":
                        pickup_action = "pickup_action_green"
                        pickup['light_color'] = "green"
                    elif pickup['pickup_type'] in  weapon_dictionary:
                        pickup_action = "pickup_action_red"    
                        pickup['light_color'] = "red"            
                    else:
                        pickup_action = "pickup_action_purple"  
                        pickup['light_color'] = "purple"     

                    pickup.replaceMesh(pickup['pickup_type'] + "_pickup")    
                    pickup.playAction(pickup_action, 0, 21, play_mode=bge.logic.KX_ACTION_MODE_LOOP)
                    own['particles'].append(pickup)
                    own['pickups'].append(pickup)
                                    
                except:
                    pickup.endObject()


def pickup_function(own):
    scene = own.scene
    
    next_generation = []
    
    weapon_dictionary = get_gun_dict()
        
    for pickup in own['pickups']:
        
        save_pickup = True
        
        if not pickup.invalid:
            
            distance = pickup.getDistanceTo(own['player_ob'])
            
            if distance < 0.6:
                pickup_pressed = key_triggered(bge.logic.globalDict['keys']["pick_up"][0])
                
                if pickup_pressed:
                    if pickup['pickup_type'] == "check_point":
                        check_point_location = pickup.worldPosition.copy()
                        check_point_location.z += 0.5
                                    
                        bge.logic.globalDict['check_point'] = check_point_location
                    
                        bge.logic.globalDict['player_dictionary'] = {}
                    
                        bge.logic.globalDict['player_dictionary']['has_jetpack'] = own['player_ob']['has_jetpack']
                        bge.logic.globalDict['player_dictionary']['has_armor'] = own['player_ob']['has_armor']
                        bge.logic.globalDict['player_dictionary']['armor'] = own['player_ob']['armor']
                        bge.logic.globalDict['player_dictionary']['health'] = own['player_ob']['health']
                        bge.logic.globalDict['player_dictionary']['weapon'] = own['player_ob']['weapon']
                        bge.logic.globalDict['player_dictionary']['weapon_ammo'] = own['player_ob']['weapon_ammo']
                                      
                                                
                    if pickup['pickup_type'] == "armor":
                        own['player_ob']['has_armor'] = True  
                        own['player_ob']['armor'] = 100 
                    if pickup['pickup_type'] == "jetpack":
                        own['player_ob']['has_jetpack'] = True   
                    if pickup['pickup_type'] == "jetpack":                    
                        own['player_ob']['has_jetpack'] = True   
                    if pickup['pickup_type'] == "ammo":
                        own['player_ob']['weapon_ammo'] = 100  
                    if pickup['pickup_type'] == "energy":
                        own['player_ob']['health'] = own['player_ob']['max_health']  
                        own['player_ob']['jet_fuel'] = own['player_ob']['max_jet_fuel']    
                         
                    if pickup['pickup_type'] in weapon_dictionary and own['player_ob']['weapon'] != "reward":
                        own['player_ob']['weapon'] =  pickup['pickup_type']  
                        own['player_ob']['weapon_ammo'] = 100    
                    
                    if pickup['pickup_type'] == "reward" or pickup['pickup_type'] =="ammo" or pickup['pickup_type'] == "check_point":
                        pickup_flash = "pickup_flash_green"
                    elif pickup['pickup_type'] in  weapon_dictionary:
                        pickup_flash = "pickup_flash_red"    
                    else:
                        pickup_flash = "pickup_flash_purple"                  
                    
                    bge.logic.globalDict['picked_up'].append(pickup.worldPosition.copy().to_tuple())
                    
                    if pickup['pickup_type'] == "check_point":
                        if bge.logic.globalDict['dead_enemies']:
                            for enemy in bge.logic.globalDict['dead_enemies']:
                                bge.logic.globalDict['cleared_enemies'].append(enemy)    
                        
                        bge.logic.globalDict['dead_enemies'] = []
                        
                        if bge.logic.globalDict['picked_up']:
                            for picked_up_item in bge.logic.globalDict['picked_up']:
                                bge.logic.globalDict['cleared_up'].append(picked_up_item)  
                        
                        bge.logic.globalDict['picked_up'] = []                     
                        
                    pickup_flash = scene.addObject(pickup_flash,pickup,0)
                    own['particles'].append(pickup_flash)
                    
                    pickup.endObject()
                    save_pickup = False


def spike_check(own):
    scene = own.scene
    
    for spike in own['spikes']:
        spike_vector = spike.worldPosition.copy() - own['player_ob'].worldPosition.copy()
        distance = spike_vector.length
        
        if distance < 1.2:
            if spike.get("top"):
                kill_states = ["JUMPING", "RUNNING", "FALLING","SCRABBLING"]
            else:
                kill_states = ["RUNNING", "FALLING"]
            
            if own['player_ob']['player_state'] in kill_states:
                dead_states = ["DYING","CRASHING","CRASHED"] 
                if own['player_ob']['player_state'] not in dead_states:                    
                    own['player_ob']['lower_hitbox']['damage'] = 21 
                    blood = scene.addObject("blood_hit",spike,0)
                    hit_sound = scene.addObject("plasma_hit_sound",spike,60) 
                    own['particles'].append(blood)


def open_doors(own):
    scene = own.scene
    
    for door in own['doors']:
                
        distance = int(door.parent.getDistanceTo(own['player_ob']))  
        
        if distance <= 3 and not door.get("locked"):
            if not door['open']:
                if not door.isPlayingAction():
                    sound = scene.addObject("door_sound",door,120)
                    door.playAction("door_action",0,10,play_mode=bge.logic.KX_ACTION_MODE_PLAY)
                    door['open'] = True
        else:
            if door['open']:
                if not door.isPlayingAction():
                    sound = scene.addObject("door_sound",door,120)
                    door.playAction("door_action",10,0,play_mode=bge.logic.KX_ACTION_MODE_PLAY)
                    door['open'] = False


def falling_bridges(own):
    scene = own.scene
    next_generation = []
    
    for bridge in own['falling_bridges']:
        distance = bridge.getDistanceTo(own['player_ob'])
        
        save_bridge = True
        
        if bridge.get('active'):
            if distance > 15:
                bridge.endObject()
                save_bridge = False
            else:            
                bridge.worldPosition.z -= 0.1
                            
        elif distance < bridge.get("distance",1.9):
            sound = scene.addObject("bridge_sound",bridge,120)
            bridge['active'] = True
            
        if save_bridge:
            next_generation.append(bridge)
            
    own['falling_bridges'] = next_generation       


def elevators(own):
    switch_tapped = key_triggered(bge.logic.globalDict['keys']["pick_up"][0],tap = True)
                   
    for elevator in own['elevators']:
        elevator_moving = False
        distance = elevator.getDistanceTo(own['player_ob'])
    
        if distance < 5.0:
            if elevator['active']:
                    
                if switch_tapped and own['player_ob']['player_state'] =="ELEVATOR_RIDING" and distance < 1.5:
                    elevator['active'] = False  
                else:     
                    own['player_ob']['on_elevator'] = True
                                    
                    if elevator['direction'] == 'UP':
                                    
                        elevator_top = elevator.worldPosition.copy()
                        elevator_top.z += 0.1
                        
                        elevator_back = elevator_top.copy()
                        elevator_back.x -= 2.0
                        
                        elevator_ray = own.rayCast(elevator_back, elevator_top, 0.0, "elevator_mount", 0, 1, 0)
                        
                        if not elevator_ray[0]:
                            elevator['active'] = False
                            elevator['direction'] = "DOWN"
                            
                        else:
                            elevator_moving = True
                                
                            elevator.worldPosition.z += 0.05             
                                        
                    else:
                        elevator_bottom = elevator.worldPosition.copy()
                        
                        elevator_back = elevator_bottom.copy()
                        elevator_back.x -= 2.0
                        
                        elevator_ray = own.rayCast(elevator_back, elevator_bottom, 0.0, "elevator_mount", 0, 1, 0)
                        
                        if not elevator_ray[0]:
                            elevator['active'] = False
                            elevator['direction'] = "UP"
                        else:
                            elevator_moving = True
                            elevator.worldPosition.z -= 0.05   
                
            else:                          
                own['player_ob']['on_elevator'] = False
                if switch_tapped and own['player_ob']['player_state'] =="IDLE":
                    if distance < 1.5:
                        elevator['active'] = True  
            
            if elevator_moving:   
                scene = own.scene
                if elevator['sound_count'] == 0: 
                    sound = scene.addObject("elevator_sound",elevator,120)
                    elevator['sound_count'] = 60
                else:
                    elevator['sound_count'] -= 1                 
        
        else:                                       
            elevator['active'] = False    


def add_screens(own):
    scene =own.scene
    
    screen_adders =  [ob for ob in scene.objects if ob.get("screen_adder")]  
    
    for adder in screen_adders:
        index = min(4,int(5.0 * bge.logic.getRandomFloat()))
        
        screen_object = "screen_" + str(index)
        
        added_screen = scene.addObject(screen_object,adder,0)
        added_screen.worldPosition.x += 0.05
        added_screen.localScale = adder.localScale
        added_screen.setParent(adder.parent)
        
        own['particles'].append(added_screen)
        
        adder.endObject()


def cam_zoom(own):
    zoom_out_pressed = key_triggered(bge.logic.globalDict['keys']["zoom_out"][0])
    zoom_in_pressed = key_triggered(bge.logic.globalDict['keys']["zoom_in"][0])
    
    current_cam_lens = own['main_cam'].lens
    
    if zoom_out_pressed and current_cam_lens > 19:
        own['main_cam'].lens -= 0.8
    if zoom_in_pressed and current_cam_lens < 120:
        own['main_cam'].lens += 0.8     


def door_locks(own):
    scene = own.scene
    switch_tapped = key_triggered(bge.logic.globalDict['keys']["pick_up"][0],tap = True)
                   
    for door_lock in own['door_locks']:        
        if not door_lock.get("used"):
            
            distance = door_lock.getDistanceTo(own['player_ob'])
            
            if switch_tapped and distance < 2.0:
                doors = [door for door in own['doors'] if door.get("locked")]
                
                doors.sort(key=door_lock.getDistanceTo)
                
                if doors[0]:
                    door_lock_effect = scene.addObject("door_lock_effect", door_lock, 0)
                    own['particles'].append(door_lock_effect)
                    doors[0]['locked'] = False
                    door_lock['used'] = True    
                
           
def level_control(cont):
    own = cont.owner
    scene = own.scene
    
    if "ini" not in own:     
        game_level = bge.logic.globalDict.get('level', 1)
        level_object = "level_" + str(game_level)
        
        level = scene.addObject(level_object, own, 0)
        
        if bge.logic.globalDict.get('check_point'):
            own.worldPosition = bge.logic.globalDict['check_point']  
        
        bge.logic.globalDict['picked_up'] = []
        bge.logic.globalDict['check_point'] = None
        bge.logic.globalDict['cleared_up'] = []
        bge.logic.globalDict['level'] = 1
        bge.logic.globalDict['dead_enemies'] = []
        bge.logic.globalDict['cleared_enemies'] = []
        
        own['main_cam'] = [ob for ob in scene.objects if ob.get("main_cam")][0]
        own['particles'] = []
        own['pickups'] = []
        own['lights'] = [ob for ob in scene.objects if ob.get("dynamic_light")]
        own['doors'] = []
                
        door_adders = [ob for ob in scene.objects if ob.get("door_adder")]
        if door_adders:
            for door_adder in door_adders:
                door_object = door_adder.get('door_type',"tall_door")
                door = scene.addObject(door_object,door_adder,0)
                own['doors'].append(door.children[0])
        
        own['elevators'] = []
                
        elevator_adders = [ob for ob in scene.objects if ob.get("elevator_adder")]
        if elevator_adders:
            for elevator_adder in elevator_adders:
                elevator_object = elevator_adder.get('elevator_type',"elevator")
                elevator = scene.addObject(elevator_object,elevator_adder,0)  
                elevator['sound_count'] = 0       
                own['elevators'].append(elevator)
                        
        own['falling_bridges'] = [ob for ob in scene.objects if ob.get("falling_bridge")]
        
        for bridge in own['falling_bridges']:
            bridge.removeParent()
        
        add_screens(own)      
                
        own['back_drop'] = [ob for ob in scene.objects if ob.get("back_drop")][0]
        
        backdrop_dict = {"1":"white_sky",
        "2":"green_sky",
        "3":"blue_sky",
        "4":"black_sky"}
        
        game_level_key = str(game_level)
                
        if game_level_key in backdrop_dict:
            mesh_name = backdrop_dict[game_level_key]
            own['back_drop'].replaceMesh(mesh_name)
        
        own['back_drop'].removeParent()
                
        pickup_setup(own)
        
        own['enemy_adders'] = [ob for ob in scene.objects if ob.get("enemy_adder")]
                        
        own['spikes'] = [ob for ob in scene.objects if ob.get("spikes")]
        
        own['exits'] = [ob for ob in scene.objects if ob.get("exit")]
        
        own['door_locks'] = [ob for ob in scene.objects if ob.get("door_lock")]
        
        own['ini'] = True
        
    else:
        if own.get('restarting'):
            restart = cont.actuators['restart']
            cont.activate(restart)

        #open_doors(own)
        #particle_control(own)

        #cam_zoom(own)
        #door_locks(own)
        #falling_bridges(own)
        #elevators(own)
        #slow_parent(own)
        #spike_check(own)
        #pickup_function(own)
        #add_enemies(own)
        #exit_check(own, cont)


def exit_check(own, cont):
    winning = cont.actuators['winning']
    clear_hud = cont.actuators['clear_hud']
    next_level = cont.actuators['next_level']
    
    if own['player_ob'].get("weapon"):
        for exit in own['exits']:
        
            distance = (own['player_ob'].worldPosition.copy() - exit.worldPosition.copy()).length
                    
            if distance < 1.5 and own['player_ob']['weapon'] == 'reward':
                cont.activate(clear_hud)    
                
                if exit['level'] != -1:
                    bge.logic.globalDict['level'] = exit['level']
                    
                    player_dictionary = {}
                    player_dictionary['has_jetpack'] = False
                    player_dictionary['has_armor'] = False
                    player_dictionary['armor'] = 0
                    player_dictionary['health'] = 100
                    player_dictionary['weapon'] = None
                    player_dictionary['weapon_ammo'] = 0
                                        
                    bge.logic.globalDict['check_point'] = None
                    bge.logic.globalDict['player_dictionary'] = player_dictionary
                    bge.logic.globalDict['picked_up'] = []
                    bge.logic.globalDict['cleared_up'] = []
                    bge.logic.globalDict['dead_enemies'] = []
                    bge.logic.globalDict['cleared_enemies'] = []
                    
                    cont.activate(next_level)
                else:                              
                    cont.activate(winning)     


def add_enemies(own):
    scene = own.scene
    next_generation = []
    
    for adder in own['enemy_adders']:
        distance = adder.getDistanceTo(own['player_ob'])
          
        save_adder = True
        
        if adder.get("level",1) != bge.logic.globalDict['difficulty']:
            save_adder = False 
        
        elif adder.worldPosition.copy().to_tuple() in bge.logic.globalDict['cleared_enemies']:
            save_adder = False  
            
        else:
            
            if distance < 15.0:
                                
                enemy_type = adder.get("enemy_type","robot_1")
                
                enemy = scene.addObject(enemy_type,adder,0)
                
                enemy['origin_key'] = adder.worldPosition.copy().to_tuple()
                            
                if enemy.get("particle"):
                    own['particles'].append(enemy)   
                
                for ob in enemy.childrenRecursive:
                    if ob.get("particle"):
                        own['particles'].append(ob)
                
                save_adder = False 
    
        if save_adder:
            next_generation.append(adder) 
    
    own['enemy_adders'] = next_generation


def get_player_objects(scene):
    return [o for o in scene.objects if o.get("player")]


def get_local_player(scene):
    return next((o for o in scene.objects if o.get("is_player")), None)


def hud_setup(cont):
    own = cont.owner
    hud_scene = own.scene
    main_scene = get_scene_by_name("main_scene")
    
    if "ini" not in own:
        if main_scene:
            level = bge.logic.globalDict.get('level',1) 
            level_text = "level " + str(level)
            
            level_label = hud_scene.addObject("level_label_ob",own,100)
            level_label['Text'] = level_text
            
            level_label.worldPosition.x -= 1.4
            level_label.worldPosition.y -= 2.5
                        
            main_control = [ob for ob in main_scene.objects if ob.get("main_control")][0]

            if not main_control.get('restarting'):
                own['jetpack_bar'] = [ob for ob in own.children if ob.get("jetpack_bar")][0]
                own['health_bar'] = [ob for ob in own.children if ob.get("health_bar")][0]
                own['armor_bar'] = [ob for ob in own.children if ob.get("armor_bar")][0]
                own['ammo_bar'] = [ob for ob in own.children if ob.get("ammo_bar")][0]
                        
                own['ini'] = True
     
    else:
        pause_tapped = key_triggered(bge.logic.globalDict['keys']["pause"][0],tap = True)
        restart_tapped = key_triggered(bge.logic.globalDict['keys']["restart_level"][0],tap = True)
        
        if pause_tapped:
            if main_scene.suspended:
                main_scene.resume()
            else:
                dead_states = ["DYING","CRASHING","CRASHED"] 

                for player_ob in get_player_objects(main_scene):
                    if player_ob['player_state'] not in dead_states:

                        for ob in main_scene.objects:
                            if ob.get("skeleton"):
                                ob.stopAction(0)
                                ob.stopAction(1)
                        main_scene.suspend()
        
        elif 0:#TODO restart_tapped or own['player_ob'].get("restart"):
            if own.get("game_over_text"):
                own['game_over_text'].endObject()      
            
            main_control = [ob for ob in main_scene.objects if ob.get("main_control")][0]
            main_control['restarting'] = True
            del own['ini'] 
            del own['game_over_text']        
        
        else:
            player_ob = get_local_player(main_scene)
            if player_ob is not None and not player_ob.invalid:
                if not own.get("game_over_text"):
                    dead_states = ["DYING", "CRASHING", "CRASHED"]

                    if player_ob['player_state'] in dead_states:
                        game_over_label = hud_scene.addObject("game_over_text",own,0)
                        game_over_label['Text'] = '        GAME OVER   \n PRESS "L" TO RE-START'

                        game_over_label.worldPosition.x -= 3.3
                        game_over_label.worldPosition.y -= 2.5

                        own['game_over_text'] = game_over_label

                if player_ob['has_jetpack']:
                    jet_factor = 1.0 / player_ob['max_jet_fuel']
                    jet_scale = player_ob['jet_fuel'] * jet_factor
                    own['jetpack_bar'].localScale.x = jet_scale
                else:
                    own['jetpack_bar'].localScale.x = 0.0

                if player_ob['weapon']:
                    ammo_factor = 1.0 / player_ob['max_weapon_ammo']
                    ammo_scale = player_ob['weapon_ammo'] * ammo_factor
                    own['ammo_bar'].localScale.x = ammo_scale
                else:
                    own['ammo_bar'].localScale.x = 0.0

                health_factor = 1.0 / player_ob['max_health']
                health_scale = player_ob['health'] * health_factor
                own['health_bar'].localScale.x = health_scale

                if player_ob['has_armor']:
                    armor_factor = 1.0 / player_ob['max_armor']
                    armor_scale = player_ob['armor'] * armor_factor
                    own['armor_bar'].localScale.x = armor_scale

                else:
                    own['armor_bar'].localScale.x = 0.0
        
        
def robot_check_collisions(own):
    local_position = own.worldPosition.copy()
    
    down_target = local_position.copy()
    down_target.z -= 0.8
    
    up_target = local_position.copy()
    up_target.z += 1.5
    
    front_target = local_position.copy()
    front_target.z -= 1.5
                   
    facing_target = local_position.copy()
    
    if own['facing'] == "right":
        facing_target.y += 1.1    
        front_target.y += 1.3
    else:
        facing_target.y -= 1.1 
        front_target.y -= 1.5
        
    wall_block_check = own.rayCast(facing_target, own, 0.0, "ground", 0, 1, 0)   
    down_check = own.rayCast(down_target, own, 0.0, "ground", 0, 1, 0)   
    front_check = own.rayCast(front_target, own, 0.0, "ground", 0, 1, 0)  
    other_robot_check = own.rayCast(facing_target, own, 0.0, "enemy", 0, 1, 0)
    
    up_check = own.rayCast(up_target, own, 0.0, "ground", 0, 1, 0)  
                        
    if down_check[0]:
        own['on_ground'] = True        
    else:  
        own['on_ground'] = False
    
    if up_check[0]:
        own['at_top'] = True
    else:
        own['at_top'] = False
            
    if not front_check[0] and own['on_ground'] and not own['flyer']:    
        own['on_edge'] = True    
    else:
        own['on_edge'] = False  
                  
    if wall_block_check[0] or other_robot_check[0]:
        own['wall_blocked'] = True
    else:
        own['wall_blocked'] = False     


def robot_movement(own,cont):
    
    target_speed = own.get("speed",2.0)
            
    if not own['flyer']:  
                    
        if own['turning']:
            own['movement'] = 0.0
            if own['turning_timer'] < 12.0:
                own['turning_timer'] += 1.0
            else:
                own['turning'] = False 
                own['turning_timer'] = 0.0       

        elif own['AI_state'] == "WALKING":
                    
            own['movement'] = target_speed * 1.0        
                                                         
        else:
            own['movement'] = 0.0

        if own['facing'] == "left" and own['movement'] != 0.0:
            own['movement'] *= -1.0
    
        if not own['on_ground']:  
            z_setting = -5.0
        else:
            z_setting = 0.0     
            
        y_setting = own['movement']       
        
    else:          
        if own['AI_state'] == "WALKING":
            own['movement'] = target_speed
        
        elif own['AI_state'] == "DYING":
            own['movement'] = -5.0
        
        elif own['AI_state'] == "DAMAGED":
            own['movement'] = 0.0    
        
        else:
            own['movement'] = target_speed * 0.5
            
        if own['facing'] == "left" and own['movement'] != 0.0 and not own['AI_state'] == "DYING":
            own['movement'] *= -1.0       
                     
        z_setting = own['movement']
        y_setting = 0.0        
        
    robot_walk = cont.actuators['robot_walk']
        
    robot_walk.linV  = [ 0.0, y_setting, z_setting]
    cont.activate(robot_walk)


def add_enemy_bullet(own):
    scene = own.scene
    
    effect = scene.addObject(own['gun_effect'],own,0)
    
    gun_hook = own['skeleton_object'].channels['gun_shooter']               
    gun_hook_matrix = gun_hook.pose_matrix.copy()            
    offset_matrix = own['skeleton_object'].worldTransform.copy()                        
    mat_out = (offset_matrix * gun_hook_matrix)
    
    effect.worldTransform = mat_out
    effect.localPosition.y += 0.5
    
    bullet = scene.addObject(own['gun_bullet'],effect,0)
        
    sound = scene.addObject(own['gun_sound'],own,0)
    
    own['main_control_object']['particles'].append(effect)
    own['main_control_object']['particles'].append(bullet)
    own['main_control_object']['particles'].append(sound)


def shoot_gun(own):
    if not False:#TODO own['main_control_object']['player_ob']['game_over']:
        
        if own['AI_state'] == "IDLE" or own['AI_state'] == "WALKING":
            
            check_target = own.worldPosition.copy()
            
            if own['facing'] == "left":
                modifier = -1.0    
            else:
                modifier = 1.0
            
            check_target.y += 100.0 * modifier
                
            player_ray = own.rayCast(check_target, own, 0.0, "player", 0, 1, 0)
            friend_ray = own.rayCast(check_target, own, 0.0, "enemy", 0, 1, 0)
            wall_ray = own.rayCast(check_target, own, 0.0, "ground", 0, 1, 0)
            
            player_distance = 200.0
            friend_distance = 100.0
            wall_distance = 100.0
            
            if player_ray[0]:  
                player_distance = (player_ray[1] - own.worldPosition.copy()).length  
                          
                if friend_ray[0]:
                    friend_distance = (friend_ray[1] - own.worldPosition.copy()).length  
                if wall_ray[0]:
                    wall_distance =  (wall_ray[1] - own.worldPosition.copy()).length      
                      
            if player_distance < friend_distance and player_distance < wall_distance:
                if own['gun_recycle'] > own['gun_recycle_time'] :
                    add_enemy_bullet(own)
                    own['gun_recycle'] = 0
                else:
                    own['gun_recycle'] += 1  


def robot_sound_cycle(own):
    scene = own.scene
    if own['sound_cycle'] == 0:
        sound = own['robot_name'] + "_sound"
        
        sound_object = scene.addObject(sound,own,120)
        
        own['sound_cycle'] = 120  
         
    else:    
        own['sound_cycle'] -= 1
                         
    
def robot_actions(cont):
    own = cont.owner
    scene = own.scene
    
    if "ini" not in own:
        
        own['AI_state'] = "IDLE"
        
        own['main_control_object'] = [ob for ob in scene.objects if ob.get("main_control")][0]
        
        own['mesh_object'] = [ob for ob in own.childrenRecursive if ob.get("mesh")][0]
        own['hook_object'] = [ob for ob in own.childrenRecursive if ob.get("hook")][0]
        own['skeleton_object'] = [ob for ob in own.childrenRecursive if ob.get("skeleton")][0]
                
        own['facing'] = "right"
        own['on_ground'] = False
        own['on_edge'] = False
        own['wall_blocked'] = False 
        own['at_top'] = False 
        
        own['being_hit'] = False
        own['hit_location'] = None
        own['damage'] = 0
        own['damage_recycle'] = 0
        own['die'] = False
        
        own['turning'] = False
        own['turning_timer'] = 0
        own['movement'] = 0.0    
        
        own['flyer'] = own.get("flyer")
        
        own['gun_recycle'] = 0
        own['gun_recycle_time'] = own.get("gun_speed",50)
        
        gun_type = own.get("gun_type","plasma") 
        
        own['gun_effect'] = gun_type + "_flash"
        own['gun_sound'] = gun_type + "_sound"
        own['gun_bullet'] = gun_type + "_bullet"
        
        own['sound_cycle'] = 0
        
        if own.get("no_gun"):
            own['bump_damage'] = 200
        else:
            own['bump_damage'] = 10 
                    
#        
#        own.addDebugProperty("on_edge")
#        own.addDebugProperty("AI_state")
#        own.addDebugProperty("turning")
#        own.addDebugProperty("facing")
#        own.addDebugProperty("on_ground")
#        own.addDebugProperty("wall_blocked")
        
        own['ini'] = True
        
    else:  
        player_bump = cont.sensors['player_bump']
        local_player = get_local_player(scene)
        
        if player_bump.positive and local_player is not None:
            dead_states = ["DYING", "CRASHING", "CRASHED"]

            if not local_player['player_state'] in dead_states:
                push_vector = local_player.worldPosition.copy() - own.worldPosition.copy()
                push_vector.length = 1.1
                local_player.worldPosition += push_vector
                
                if own.get("no_gun"):
                    bump_effect = "blood_hit"
                    bump_sound = "sparks_sound"#TODO this might be changed

                else:
                    bump_effect = "sparks_hit"
                    bump_sound = "sparks_sound"
              
                local_player['lower_hitbox']['damage'] = own['bump_damage']
                blood = scene.addObject(bump_effect,own,0)
                hit_sound = scene.addObject(bump_sound,own,60) 
                own['main_control_object']['particles'].append(blood)
                    
        robot_sound_cycle(own)                         
        robot_check_collisions(own)
        robot_movement(own,cont)
        align_to_facing(own)
        
        if not own.get("no_gun"):
            shoot_gun(own)
        
        if own['AI_state'] == "IDLE":            
            own['skeleton_object'].playAction(own['default_ani'], 0, 120, priority=1, blendin=12, play_mode=bge.logic.KX_ACTION_MODE_LOOP)
            
            if local_player is not None:#TODO  and not local_player['game_over']:
                                     
                if own['being_hit']:
                    own['AI_state'] = "DAMAGED"                
                
                else:    
                    if not own['flyer']:                                    
                        if own['on_ground'] and not own['wall_blocked'] and not own['on_edge']:           
                            own['AI_state'] = "WALKING"
                            
                        else:
                            if not own['turning']:                
                                if own['facing'] == "left":
                                    own['facing'] = "right"
                                elif own['facing'] == "right":
                                    own['facing'] = "left"  
                                own['turning'] = True
                    
                    else:
                        if own['on_ground']:
                            if not own['turning']:
                                own['facing'] = "right"  
                        elif own['at_top']:
                            if not own['turning']:
                                own['facing'] = "left" 
                        else:
                            own['AI_state'] = "WALKING" 

        if own['AI_state'] == "WALKING":
            
            if own['main_control_object']['player_ob']['game_over']:
                own['AI_state'] = "IDLE"    
            
            elif own['being_hit']:
                own['AI_state'] = "DAMAGED"                
            
            else:  
                own['skeleton_object'].playAction(own['walk_ani'], 0, 21, priority=1, blendin=12, play_mode=bge.logic.KX_ACTION_MODE_LOOP)
                 
                
                if not own['flyer']:     
                    if own['wall_blocked'] or own['on_edge']:                
                        own['AI_state'] = "IDLE"  
                else:
                    if own['at_top'] or own['on_ground']:                
                        own['AI_state'] = "IDLE"              

        if own['AI_state'] == "DAMAGED":   
            if own['being_hit']:
                own['skeleton_object'].stopAction(1)
                own['health'] -= own['damage']
                own['damage'] = 0
                own['damage_recycle'] = 0
                own['being_hit'] = False
            
            if own['health'] < 0.0:
                own['AI_state'] = "DYING"      
            else:
                own['skeleton_object'].playAction(own['hit_ani'], 0, 21, priority=1, blendin=12, play_mode=bge.logic.KX_ACTION_MODE_LOOP)
                                 
                if own['damage_recycle'] > 40:
                    own['AI_state'] = "IDLE"
                    own['damage_recycle'] = 0
                else:    
                    own['damage_recycle'] += 1
                   
        if own['AI_state'] == "DYING":
            if not own['skeleton_object'].isPlayingAction() and own['die']:
                bge.logic.globalDict['dead_enemies'].append(own['origin_key'])
                
                own.endObject()
            else: 
                if not own['die']: 
                    for i in range(6):
                        trash = "trash_" + str(i)
                        trash_object = scene.addObject(trash,own,0)
                        own['main_control_object']['particles'].append(trash_object)
                    
                    collision_hit = scene.addObject("collision_hit",own,0)   
                    own['main_control_object']['particles'].append(collision_hit)
                    
                    collision_hit_sound = scene.addObject("collision_hit_sound",own,60)
                    
                        
                    own['mesh_object'].replaceMesh(own['die_mesh'])
                    own['skeleton_object'].playAction(own['die_ani'], 0, 50, priority=1, blendin=12, play_mode=bge.logic.KX_ACTION_MODE_PLAY)
                                 
                    own.replaceMesh("dead_robot_mesh",False,True)
                    
                    own['die'] = True


def mouse_triggered(button): 
    mouse = bge.logic.mouse
    tapped = bge.logic.KX_INPUT_JUST_ACTIVATED 
        
    if mouse.events[button] == tapped:
        return True
    
    return False


def mouse_hit_ray(camera,mouse_position,property):
    screen_vect = camera.getScreenVect(*mouse_position)      
    target_position = camera.worldPosition - screen_vect                
    target_ray = camera.rayCast( target_position, camera, 300.0, property, 0, 1, 0)
        
    return target_ray


def setup_game(cont):
    default_keys =  {"walk_left":(113,"QKEY"),
	"jump":(119,"WKEY"),
	"walk_right":(101,"EKEY"),
	"run_left":(97,"AKEY"),
	"crouch":(115,"SKEY"),
	"run_right":(100,"DKEY"),
	"pick_up":(102,"FKEY"),
	"pause":(112,"PKEY"),
	"restart_level":(108,"LKEY"),
	"shoot":(32,"SPACEKEY"),
    "zoom_out":(159,"PADMINUS"),
    "zoom_in":(161,"PADPLUSKEY")} 
                            
    own = cont.owner
    scene = own.scene
    
    if "ini" not in own:   
        bge.render.showMouse(True)

        own['key_objects'] = [ob for ob in scene.objects if ob.get("key_object")]
        own['difficult_objects'] = [ob for ob in scene.objects if ob.get("difficulty")]
        own['key_dict'] = default_keys
                
        for startup_key in own['key_objects']:
            key_text = startup_key.children[0]
            key_text.color = [1.0,1.0,1.0,1.0]  
            key_text.localScale = [0.15,0.15,0.15]
            key_text.resolution = 8   
        
        for ob in scene.objects:
            ob.visible = True
               
        own['ini'] = True    
            
    else:        
        left_button = mouse_triggered(bge.events.LEFTMOUSE)     
        mouse_position = bge.logic.mouse.position 
        
        difficulty_over = mouse_hit_ray(own,mouse_position,"difficulty")
        keyboard_over = mouse_hit_ray(own,mouse_position,"key_object")
        exit_over = mouse_hit_ray(own,mouse_position,"save")
        
        red_color = [0.3, 0.01, 0.02, 1.0]
        green_color = [0.05, 0.3, 0.08, 1.0]
        
        active_mapping_key = None
        
        if difficulty_over[0] and left_button:
            for difficult_object in own['difficult_objects'] :
                if difficult_object == difficulty_over[0]:
                    difficult_object['active'] = True
                else:
                    difficult_object['active'] = False   
       
        if keyboard_over[0] and left_button:
            for key_object in own['key_objects']:
                if key_object == keyboard_over[0]:
                    key_object['active'] = True
                else:
                    key_object['active'] = False  
                    
        for check_key in own['key_objects']:
            key_text = check_key.children[0]
                
            dict_entry = own['key_dict'].get(check_key['key_name'])
            
            if dict_entry:
                dict_entry_text = dict_entry[1]
            else:
                dict_entry_text = ""
            
            text_string = check_key['key_name']
            string_objects = text_string.split("_")
            
            if len(string_objects) < 2:
                string_objects.append("")
                
            string_objects.append(dict_entry_text)
            
            display_string = ""
                    
            for string_item in string_objects:
                display_string += string_item 
                display_string += "\n"         
            
            key_text['Text'] = display_string        
            
            if check_key['active']:
                check_key.color = green_color
                check_key.worldPosition.z = -0.2    
                            
            else:
                check_key.color = red_color
                check_key.worldPosition.z = 0.0
                    
        for check_difficulty in own['difficult_objects'] :
            if check_difficulty['active']:
                check_difficulty.color = green_color
                check_difficulty.worldPosition.z = -0.2

            else:
                check_difficulty.color = red_color
                check_difficulty.worldPosition.z = 0.0
                                                        
        active_key = None
        
        for assign_key in own['key_objects']:
            if assign_key['active']:
                active_key = assign_key
                
        current_pressed_key = None                   
        keys_pressed = bge.logic.keyboard.events
            
        for pressed_key in keys_pressed:
            
            if keys_pressed[pressed_key] == 1:
                current_pressed_key = pressed_key    
        
        if current_pressed_key and active_key:   
            own['key_dict'][active_key['key_name']] = (current_pressed_key,bge.events.EventToString(current_pressed_key))
            
        if exit_over[0] and left_button:
            save_options(own)

            bge.render.showMouse(False)
                    
            start_game = cont.actuators['start_game']        
            cont.activate(start_game)


def save_options(own):
    active_difficulty = [key for key in own['difficult_objects'] if key['active']][0]
    difficulty = active_difficulty['level']

    player_dictionary = {}
    player_dictionary['has_jetpack'] = False
    player_dictionary['has_armor'] = False
    player_dictionary['armor'] = 0
    player_dictionary['health'] = 100
    player_dictionary['weapon'] = None
    player_dictionary['weapon_ammo'] = 0
    bge.logic.globalDict['player_dictionary'] = player_dictionary

    bge.logic.globalDict['difficulty'] = difficulty
    bge.logic.globalDict['keys'] = own['key_dict']


def winner(cont):
    
    own = cont.owner
    scene = own.scene
    
    level = bge.logic.globalDict['difficulty']       
    
    mars = [ob for ob in scene.objects if ob.get("mars")][0]
    
    red = [1.0,0.0,0.0,1.0]
    green = [0.0,1.0,0.0,1.0]
    
    if level == 1:
        mars.color = green
        own['Text']  = "EASY \n MODE"
        own.color = green 
    else:
        mars.color = red
        own['Text']  = "HARD \n MODE"
        own.color = red