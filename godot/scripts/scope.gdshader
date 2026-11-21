shader_type canvas_item;
render_mode unshaded;

void fragment() {
	vec2 at = UV - vec2(0.5);
	at.x *= SCREEN_PIXEL_SIZE.y / SCREEN_PIXEL_SIZE.x;
	float radius = length(at);
	float edge = smoothstep(0.402, 0.417, radius);
	float reticle = 1.0 - smoothstep(0.00055, 0.00125, min(abs(at.x), abs(at.y)));
	float vignette = smoothstep(0.31, 0.414, radius) * 0.56;
	COLOR = vec4(0.014, 0.019, 0.024, max(edge, max(reticle, vignette)));
}
