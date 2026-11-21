shader_type spatial;
render_mode unshaded, cull_disabled, shadows_disabled;

varying vec3 world_point;

void vertex() {
	world_point = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
}

void fragment() {
	vec3 n = normalize(cross(dFdx(world_point), dFdy(world_point)));
	float flatness = abs(n.y);
	float light = 0.62 + abs(dot(n, normalize(vec3(0.35, 0.9, 0.15)))) * 0.38;
	vec3 sand = vec3(0.61, 0.49, 0.34);
	vec3 plaster = vec3(0.78, 0.71, 0.58);
	vec3 grid = abs(fract(world_point + vec3(0.5)) - 0.5) / max(fwidth(world_point), vec3(0.001));
	vec3 line = 1.0 - smoothstep(vec3(0.0), vec3(1.2), grid);
	vec3 visible = line * (1.0 - abs(n));
	ALBEDO = mix(plaster, sand, pow(flatness, 3.0)) * light - max(max(visible.x, visible.y), visible.z) * 0.1;
}
