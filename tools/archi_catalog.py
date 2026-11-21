"""The combat viewmodels shipped by the pinned Archi pack."""
EXTRA_MODELS = {
    'cz75': ('cz75a', 'v_pist_cz_75', {}), 'dual-berettas': ('elite', 'v_pist_elite', {'shoot1': 'shoot_left1', 'shoot2': 'shoot_right1'}),
    'five-seven': ('fiveseven', 'v_pist_fiveseven', {}), 'p2000': ('p2000', 'v_pist_hkp2000', {}),
    'p250': ('p250', 'v_pist_p250', {}), 'r8': ('revolver', 'v_pist_revolver', {'shoot1': 'fire', 'shoot2': 'alt1', 'shoot3': 'alt2'}),
    'tec-9': ('tec9', 'v_pist_tec9', {}), 'zeus': ('taser', 'v_eq_taser', {}),
    'aug': ('aug', 'v_rif_aug', {}), 'famas': ('famas', 'v_rif_famas', {}),
    'g3sg1': ('g3sg1', 'v_snip_g3sg1', {'idle': 'idle1', 'shoot1': 'shoot'}),
    'galil': ('galilar', 'v_rif_galilar', {}), 'm4a1-s': ('m4a1s', 'v_rif_m4a1_s', {'silencer_attach': 'attach', 'silencer_detach': 'detach'}),
    'scar-20': ('scar20', 'v_snip_scar20', {}), 'sg-553': ('sg556', 'v_rif_sg556', {}),
    'ssg-08': ('ssg08', 'v_snip_ssg08', {'idle': 'idle1', 'shoot1': 'shoot'}),
    'bizon': ('bizon', 'v_smg_bizon', {'idle': 'bizon_idle', 'shoot1': 'bizon_fire1', 'draw': 'bizon_draw', 'reload': 'bizon_reload'}),
    'mac-10': ('mac10', 'v_smg_mac10', {'idle': 'mac10_idle', 'shoot1': 'mac10_fire', 'shoot2': 'mac10_fire2', 'shoot3': 'mac10_fire3', 'draw': 'mac10_draw', 'reload': 'mac10_reload'}),
    'mp5-sd': ('mp5sd', 'v_smg_mp5sd', {'shoot1': 'shoot'}), 'mp7': ('mp7', 'v_smg_mp7', {}),
    'mp9': ('mp9', 'v_smg_mp9', {'idle': 'idle1', 'shoot1': 'fire1', 'shoot2': 'fire2', 'shoot3': 'fire3'}),
    'p90': ('p90', 'v_smg_p90', {}), 'ump-45': ('ump45', 'v_smg_ump45', {'idle': 'idle1'}),
    'm249': ('m249', 'v_mach_m249para', {'idle': 'idle1'}), 'negev': ('negev', 'v_mach_negev', {'idle': 'idle1'}),
    'mag-7': ('mag7', 'v_shot_mag7', {'shoot1': 'shoot2'}), 'nova': ('nova', 'v_shot_nova', {}),
    'sawed-off': ('sawedoff', 'v_shot_sawedoff', {}), 'xm1014': ('xm1014', 'v_shot_xm1014', {}),
}
TUBE_SHOTGUNS = {'nova', 'sawed-off', 'xm1014'}
SILENCERS = {'usp-s', 'm4a1-s'}
