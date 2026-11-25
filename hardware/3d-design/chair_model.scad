// 迷你靠背椅（与 table_model.scad 配套，默认约 1:10 比例）
// 所有尺寸单位：毫米（mm）。可以修改参数后重新导出 STL。
$fn = 48;

CHAIR_WIDTH = 44;
CHAIR_DEPTH = 42;
CHAIR_TOTAL_HEIGHT = 84;
SEAT_TOP_HEIGHT = 43;
SEAT_THICKNESS = 5;
SEAT_CORNER_RADIUS = 4;
LEG_SIZE = 7;
LEG_INSET = 2;
BACKREST_THICKNESS = 5;
BACKREST_TOP_HEIGHT = 84;
BACKREST_BAND_HEIGHT = 15;
LOWER_SLAT_BASE_HEIGHT = 54;
LOWER_SLAT_HEIGHT = 7;

module rounded_plate(w, d, thickness, r) {
    linear_extrude(height = thickness)
        offset(r = r)
            square([w - 2*r, d - 2*r], center = true);
}

module miniature_chair() {
    seat_base_z = SEAT_TOP_HEIGHT - SEAT_THICKNESS;
    post_x = CHAIR_WIDTH/2 - LEG_INSET - LEG_SIZE/2;
    post_y = CHAIR_DEPTH/2 - LEG_INSET - LEG_SIZE/2;
    union() {
        // 平整圆角坐板
        translate([0, 0, seat_base_z])
            rounded_plate(CHAIR_WIDTH, CHAIR_DEPTH, SEAT_THICKNESS, SEAT_CORNER_RADIUS);
        // 前腿，进入坐板 2 mm
        for (x = [-post_x, post_x])
            translate([x, -post_y, (seat_base_z + 2)/2])
                cube([LEG_SIZE, LEG_SIZE, seat_base_z + 2], center = true);
        // 后腿向上延伸为靠背立柱
        for (x = [-post_x, post_x])
            translate([x, post_y, CHAIR_TOTAL_HEIGHT/2])
                cube([LEG_SIZE, LEG_SIZE, CHAIR_TOTAL_HEIGHT], center = true);
        // 宽上靠背板，与两端立柱有搭接
        translate([0, post_y, BACKREST_TOP_HEIGHT - BACKREST_BAND_HEIGHT/2])
            cube([2*post_x + 2, BACKREST_THICKNESS, BACKREST_BAND_HEIGHT], center = true);
        // 下靠背横条
        translate([0, post_y, LOWER_SLAT_BASE_HEIGHT + LOWER_SLAT_HEIGHT/2])
            cube([2*post_x + 2, BACKREST_THICKNESS, LOWER_SLAT_HEIGHT], center = true);
    }
}

miniature_chair();
