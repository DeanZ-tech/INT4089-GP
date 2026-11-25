// 迷你四脚桌（默认约 1:10 比例）
// 所有尺寸单位：毫米（mm）。可以直接修改这些参数后重新导出 STL。
$fn = 48;

TABLE_WIDTH = 110;
TABLE_DEPTH = 66;
TABLE_HEIGHT = 72;
TOP_THICKNESS = 5;
TOP_CORNER_RADIUS = 6;
LEG_SIZE = 8;
LEG_INSET = 7;             // 桌腿中心到顶板边缘的额外退让距离（与半腿宽叠加）
APRON_HEIGHT = 11;
APRON_THICKNESS = 5;

module rounded_plate(w, d, thickness, r) {
    linear_extrude(height = thickness)
        offset(r = r)
            square([w - 2*r, d - 2*r], center = true);
}

module miniature_table() {
    top_bottom_z = TABLE_HEIGHT - TOP_THICKNESS;
    leg_x = TABLE_WIDTH/2 - LEG_INSET - LEG_SIZE/2;
    leg_y = TABLE_DEPTH/2 - LEG_INSET - LEG_SIZE/2;
    union() {
        // 圆角桌面
        translate([0, 0, top_bottom_z])
            rounded_plate(TABLE_WIDTH, TABLE_DEPTH, TOP_THICKNESS, TOP_CORNER_RADIUS);
        // 四条桌腿，伸入桌板 2 mm 以保证布尔合并稳定
        for (x = [-leg_x, leg_x], y = [-leg_y, leg_y])
            translate([x, y, (top_bottom_z + 2)/2])
                cube([LEG_SIZE, LEG_SIZE, top_bottom_z + 2], center = true);
        // 前后围板（与腿柱重叠，增强模型结构）
        for (y = [-leg_y, leg_y])
            translate([0, y, top_bottom_z - APRON_HEIGHT/2 + 1])
                cube([2*leg_x + 2, APRON_THICKNESS, APRON_HEIGHT + 2], center = true);
        // 左右围板
        for (x = [-leg_x, leg_x])
            translate([x, 0, top_bottom_z - APRON_HEIGHT/2 + 1])
                cube([APRON_THICKNESS, 2*leg_y + 2, APRON_HEIGHT + 2], center = true);
    }
}

miniature_table();
