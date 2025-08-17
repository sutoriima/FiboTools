bl_info = {
    "name":        "FiboTools",
    "author":      "SutoRiima",
    "version":     (1, 0, 0),
    "blender":     (4, 0, 0),
    "location":    "View3D > Sidebar > FiboTools",
    "description": "Generate bones, split bones, and mesh cuts at Fibonacci ratios.",
    "category":    "Rigging",
}

import bpy
import bmesh
from mathutils import Vector

# 共通
def fibonacci_sequence(n):
    if n < 1:
        return []
    seq = [1, 1]
    while len(seq) < n+1:
        seq.append(seq[-1] + seq[-2])
    # 先頭の1を除外
    return seq[1:n+1]

def fibonacci_ratios(count, reverse=False, blend=1.0):
    fibs = fibonacci_sequence(count)
    base = [1] * count
    weights = [(1-blend)*b + blend*f for b, f in zip(base, fibs)]
    total = sum(weights)
    ratios = []
    cum = 0.0２
    for w in weights:
        cum += w
        ratios.append(cum/total)
    # 端点（0, 1）は含めない
    ratios = ratios[:-1]
    ratios = list(reversed(ratios))
    if reverse:
        ratios = list(reversed(ratios))
    return ratios

# パネル設定
class FibSettings(bpy.types.PropertyGroup):
    split_count: bpy.props.IntProperty(name="Segments/Cuts", default=5, min=2, max=100)
    mix_percent: bpy.props.FloatProperty(name="Blend (%)", default=50.0, min=0.0, max=100.0)
    reverse_order: bpy.props.BoolProperty(name="Reverse Order", default=False)
    bone_chain: bpy.props.BoolProperty(name="Connect Chain", default=True)
    bone_prefix: bpy.props.StringProperty(name="Bone Prefix", default="Bone")
    target_armature: bpy.props.PointerProperty(
        name="Target Armature",
        type=bpy.types.Object,
        poll=lambda self, obj: obj.type == 'ARMATURE'
    )

# Curve→Bone生成
class FIB_OT_initialize_armature(bpy.types.Operator):
    bl_idname = "armature.fib_initialize_armature"
    bl_label = "Initialize (Add Armature)"
    bl_options = {'REGISTER', 'UNDO'}

    armature_name: bpy.props.StringProperty(
        name="Armature Name",
        default="FiboArmature"
    )

    def execute(self, context):
        arm_name = self.armature_name
        for obj in bpy.data.objects:
            if obj.name == arm_name and obj.type == 'ARMATURE':
                used_in_scene = any(obj.name in s.objects for s in bpy.data.scenes)
                if obj.users <= 1 and not used_in_scene:
                    data = obj.data
                    bpy.data.objects.remove(obj, do_unlink=True)
                    if data and data.users <= 0:
                        bpy.data.armatures.remove(data)
        for a in bpy.data.armatures:
            if a.name == arm_name and a.users <= 0:
                bpy.data.armatures.remove(a)
        arm_data = bpy.data.armatures.new(arm_name)
        arm_obj  = bpy.data.objects.new(arm_name, arm_data)
        context.collection.objects.link(arm_obj)
        context.window_manager.fib_settings.target_armature = arm_obj
        self.report({'INFO'}, f"New Armature '{arm_obj.name}' created and set")
        return {'FINISHED'}

class FIB_OT_from_curve(bpy.types.Operator):
    bl_idname = "armature.fib_bone_from_curve"
    bl_label = "Generate Fibonacci Bones"
    bl_options = {'REGISTER', 'UNDO'}

    split_count: bpy.props.IntProperty(name="Segments/Cuts", default=5, min=2, max=100)
    mix_percent: bpy.props.FloatProperty(name="Blend (%)", default=50.0, min=0.0, max=100.0)
    reverse_order: bpy.props.BoolProperty(name="Reverse Order", default=False)
    bone_chain: bpy.props.BoolProperty(name="Connect Chain", default=True)
    bone_prefix: bpy.props.StringProperty(name="Bone Prefix", default="Bone")

    def execute(self, context):
        s = context.window_manager.fib_settings
        curve = context.active_object
        if not curve or curve.type != 'CURVE':
            self.report({'ERROR'}, "Active object must be a Curve")
            return {'CANCELLED'}
        arm_obj = s.target_armature
        if not arm_obj or arm_obj.type != 'ARMATURE':
            self.report({'ERROR'}, "Target Armature is not set or invalid")
            return {'CANCELLED'}
        n = self.split_count
        factor = self.mix_percent / 100.0
        reverse_order = self.reverse_order
        bone_chain = self.bone_chain
        bone_prefix = self.bone_prefix
        arm_data = arm_obj.data

        deps = context.evaluated_depsgraph_get()
        eval_obj = curve.evaluated_get(deps)
        mesh = eval_obj.to_mesh()
        if not mesh or len(mesh.vertices) < 2:
            self.report({'ERROR'}, "Failed to evaluate curve")
            return {'CANCELLED'}

        pts = [eval_obj.matrix_world @ v.co for v in mesh.vertices]
        eval_obj.to_mesh_clear()

        fib = fibonacci_sequence(n)
        if not reverse_order:
            fib.reverse()
        base = [1]*n
        weights = [(1-factor)*b + factor*f for b, f in zip(base, fib)]
        total = sum(weights)
        cum = 0.0
        fracs = []
        for w in weights:
            cum += w
            fracs.append(cum/total)
        fracs = [0.0] + fracs
        if fracs[-1] < 1.0:
            fracs.append(1.0)
        dist = [(pts[i] - pts[i-1]).length for i in range(1, len(pts))]
        cumd = [0.0]
        for d in dist:
            cumd.append(cumd[-1] + d)
        length = cumd[-1]
        if length == 0:
            self.report({'ERROR'}, "Curve has zero length")
            return {'CANCELLED'}
        split_pts = []
        for f in fracs:
            target = f * length
            for i in range(1, len(cumd)):
                if cumd[i] >= target:
                    seg_len = cumd[i] - cumd[i-1]
                    t = (target - cumd[i-1]) / seg_len if seg_len > 0 else 0.0
                    split_pts.append(pts[i-1].lerp(pts[i], t))
                    break

        bpy.ops.object.mode_set(mode='OBJECT')
        context.view_layer.objects.active = arm_obj
        arm_obj.select_set(True)
        bpy.ops.object.mode_set(mode='EDIT')

        prev_bone = None
        prev_pt = split_pts[0]
        for i, pt in enumerate(split_pts[1:], start=1):
            name = f"{bone_prefix}.{i:03d}"
            eb = arm_data.edit_bones.new(name)
            eb.head = prev_pt
            eb.tail = pt
            if bone_chain and prev_bone:
                eb.parent = prev_bone
                eb.use_connect = True
            prev_bone = eb
            prev_pt = pt

        bpy.ops.object.mode_set(mode='OBJECT')
        self.report({'INFO'}, f"Generated {len(split_pts)-1} bones in '{arm_obj.name}'")
        return {'FINISHED'}

    def invoke(self, context, event):
        s = context.window_manager.fib_settings
        self.split_count = s.split_count
        self.mix_percent = s.mix_percent
        self.reverse_order = s.reverse_order
        self.bone_chain = s.bone_chain
        self.bone_prefix = s.bone_prefix
        return self.execute(context)

class FIB_OT_split_bone_fibonacci(bpy.types.Operator):
    bl_idname = "armature.split_bone_fibonacci"
    bl_label = "Split Bones Fibonacci"
    bl_options = {'REGISTER', 'UNDO'}

    split_count: bpy.props.IntProperty(name="Segments/Cuts", default=5, min=2, max=100)
    mix_percent: bpy.props.FloatProperty(name="Blend (%)", default=50.0, min=0.0, max=100.0)
    reverse_order: bpy.props.BoolProperty(name="Reverse Order", default=False)
    bone_chain: bpy.props.BoolProperty(name="Connect Chain", default=True)

    def execute(self, context):
        s = context.window_manager.fib_settings
        ebones = context.active_object.data.edit_bones
        sel = [b for b in ebones if b.select]
        if not sel:
            self.report({'ERROR'}, "Select at least one bone")
            return {'CANCELLED'}
        n = self.split_count
        fib = fibonacci_sequence(n)
        if not self.reverse_order:
            fib.reverse()
        base = [1]*n
        factor = self.mix_percent / 100.0
        weights = [(1-factor)*b + factor*f for b, f in zip(base, fib)]
        total = sum(weights)
        for bone in sel:
            head, tail = bone.head.copy(), bone.tail.copy()
            direction = tail - head
            name = bone.name
            parent = bone.parent
            conn   = bone.use_connect
            children = [c for c in ebones if c.parent == bone]
            ebones.remove(bone)
            cum = 0.0
            pts = []
            for w in weights:
                cum += w
                pts.append(head + direction*(cum/total))
            prev = None
            prev_h = head
            new_bones = []
            for i, pt in enumerate(pts, start=1):
                bn = ebones.new(f"{name}.{i:03d}")
                bn.head = prev_h
                bn.tail = pt
                if i == 1 and parent:
                    bn.parent = parent
                    bn.use_connect = conn
                elif self.bone_chain and prev:
                    bn.parent = prev
                    bn.use_connect = True
                prev = bn
                prev_h = pt
                new_bones.append(bn)
            if children and new_bones:
                last = new_bones[-1]
                for c in children:
                    c.parent = last
                    c.use_connect = True
        self.report({'INFO'}, "Bones split by Fibonacci")
        return {'FINISHED'}

    def invoke(self, context, event):
        s = context.window_manager.fib_settings
        self.split_count = s.split_count
        self.mix_percent = s.mix_percent
        self.reverse_order = s.reverse_order
        self.bone_chain = s.bone_chain
        return self.execute(context)

# メッシュ面フィボナッチ分割 ctrl+R法則＋Redoパネル
class FIB_OT_fibonacci_face_cut(bpy.types.Operator):
    bl_idname = "mesh.fibonacci_face_cut"
    bl_label = "Fibonacci Face Cut"
    bl_options = {'REGISTER', 'UNDO'}

    split_count: bpy.props.IntProperty(name="Segments/Cuts", default=5, min=2, max=100)
    mix_percent: bpy.props.FloatProperty(name="Blend (%)", default=50.0, min=0.0, max=100.0)
    reverse_order: bpy.props.BoolProperty(name="Reverse Order", default=False)

    def execute(self, context):
        obj = context.active_object
        if not obj or obj.type != 'MESH' or context.mode != 'EDIT_MESH':
            self.report({'ERROR'}, "Edit Mesh mode & mesh object required")
            return {'CANCELLED'}
        bm = bmesh.from_edit_mesh(obj.data)
        sel_faces = [f for f in bm.faces if f.select]
        if not sel_faces:
            self.report({'ERROR'}, "Select at least one face")
            return {'CANCELLED'}

        ratios = fibonacci_ratios(self.split_count, reverse=self.reverse_order, blend=self.mix_percent/100.0)
        split_count = len(ratios)
        total_inserted = 0
        for face in sel_faces:
            bm.verts.ensure_lookup_table()
            verts = face.verts
            if len(verts) != 4:
                self.report({'ERROR'}, "Only quad faces are supported for now")
                continue
            v0, v1, v2, v3 = verts[0], verts[1], verts[2], verts[3]
            # AB, DCエッジ取得
            ab_edge = None
            dc_edge = None
            for e in face.edges:
                if (v0 in e.verts and v1 in e.verts):
                    ab_edge = e
                elif (v2 in e.verts and v3 in e.verts):
                    dc_edge = e
            if not ab_edge or not dc_edge:
                self.report({'ERROR'}, "Failed to find AB/DC edges")
                continue
            ab_points = [v0.co.lerp(v1.co, r) for r in ratios]
            dc_points = [v3.co.lerp(v2.co, r) for r in ratios]
            # 分割点を一括生成
            ab_new_verts = [bm.verts.new(pt) for pt in ab_points]
            dc_new_verts = [bm.verts.new(pt) for pt in dc_points]
            bm.verts.index_update()
            bm.verts.ensure_lookup_table()
            # ABエッジ分割（元のab_edge/v0を使い続ける）
            ab_split_verts = []
            for pt in ab_points:
                # ab_edgeの端点を動的に判定
                v_a, v_b = ab_edge.verts[0], ab_edge.verts[1]
                # v0に近い方を基準
                if (v_a.co - v0.co).length < (v_b.co - v0.co).length:
                    base_v = v_a
                    other_v = v_b
                else:
                    base_v = v_b
                    other_v = v_a
                ab_len = (other_v.co - base_v.co).length
                fraction = (pt - base_v.co).length / ab_len if ab_len > 0 else 0.0
                result = bmesh.utils.edge_split(ab_edge, base_v, fraction)
                ab_split_verts.append(result[1])
                ab_edge = result[0]  # edgeは更新
                total_inserted += 1
            dc_split_verts = []
            for pt in dc_points:
                v_a, v_b = dc_edge.verts[0], dc_edge.verts[1]
                # v3に近い方を基準
                if (v_a.co - v3.co).length < (v_b.co - v3.co).length:
                    base_v = v_a
                    other_v = v_b
                else:
                    base_v = v_b
                    other_v = v_a
                dc_len = (other_v.co - base_v.co).length
                fraction = (pt - base_v.co).length / dc_len if dc_len > 0 else 0.0
                result = bmesh.utils.edge_split(dc_edge, base_v, fraction)
                dc_split_verts.append(result[1])
                dc_edge = result[0]
                total_inserted += 1
            # 分割点をv0→v1, v3→v2方向でソート
            ab_dir = (v1.co - v0.co).normalized()
            ab_split_verts_sorted = sorted(ab_split_verts, key=lambda v: (v.co - v0.co).dot(ab_dir))
            dc_dir = (v2.co - v3.co).normalized()
            dc_split_verts_sorted = sorted(dc_split_verts, key=lambda v: (v.co - v3.co).dot(dc_dir))
            # 順序保証して面生成
            all_ab = [v0] + ab_split_verts_sorted + [v1]
            all_dc = [v3] + dc_split_verts_sorted + [v2]
            for i in range(split_count+1):
                quad_verts = [all_ab[i], all_ab[i+1], all_dc[i+1], all_dc[i]]
                try:
                    bm.faces.new(quad_verts)
                except ValueError:
                    pass  # 既存面はスキップ
            bm.faces.remove(face)
        bm.verts.index_update()
        bm.verts.ensure_lookup_table()
        bm.faces.index_update()
        bm.faces.ensure_lookup_table()
        # 法線再計算
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        bmesh.update_edit_mesh(obj.data)
        self.report({'INFO'}, f"Inserted {total_inserted} split points and subdivided faces.")
        return {'FINISHED'}

    def invoke(self, context, event):
        s = context.window_manager.fib_settings
        self.split_count = s.split_count
        self.mix_percent = s.mix_percent
        self.reverse_order = s.reverse_order
        return self.execute(context)

# パネル
class VIEW3D_PT_fib_tools(bpy.types.Panel):
    bl_label = "FiboTools"
    bl_idname = "VIEW3D_PT_fib_tools"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "FiboTools"

    def draw(self, context):
        s = context.window_manager.fib_settings
        layout = self.layout

        # 共通パラメータ
        box = layout.box()
        box.label(text="Fibonacci Parameters")
        box.prop(s, "split_count")
        box.prop(s, "mix_percent")
        box.prop(s, "reverse_order")

        # Curve → Fibonacci Bones
        box = layout.box()
        box.label(text="Curve → Fibonacci Bones")
        box.prop(s, "bone_prefix")
        box.prop(s, "bone_chain")
        box.prop(s, "target_armature")
        box.operator(FIB_OT_initialize_armature.bl_idname, text="Initialize (Add Armature)")
        op_curve = box.operator(FIB_OT_from_curve.bl_idname, text="Generate Bones")
        op_curve.split_count = s.split_count
        op_curve.mix_percent = s.mix_percent
        op_curve.reverse_order = s.reverse_order
        op_curve.bone_chain = s.bone_chain
        op_curve.bone_prefix = s.bone_prefix

        # Split Selected Bones
        box = layout.box()
        box.label(text="Split Selected Bones")
        box.prop(s, "bone_chain")
        op_split = box.operator(FIB_OT_split_bone_fibonacci.bl_idname, text="Split Bones")
        op_split.split_count = s.split_count
        op_split.mix_percent = s.mix_percent
        op_split.reverse_order = s.reverse_order
        op_split.bone_chain = s.bone_chain

        # Mesh Fibonacci Face Cut（第3の機能, ctrl+R法則）
        box = layout.box()
        box.label(text="Fibonacci Face Cut (Mesh)")
        op_cut = box.operator(FIB_OT_fibonacci_face_cut.bl_idname, text="Apply Fibonacci Face Cut")
        op_cut.split_count = s.split_count
        op_cut.mix_percent = s.mix_percent
        op_cut.reverse_order = s.reverse_order

classes = (
    FibSettings,
    FIB_OT_initialize_armature,
    FIB_OT_from_curve,
    FIB_OT_split_bone_fibonacci,
    FIB_OT_fibonacci_face_cut,
    VIEW3D_PT_fib_tools,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.WindowManager.fib_settings = bpy.props.PointerProperty(type=FibSettings)

def unregister():
    del bpy.types.WindowManager.fib_settings
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

if __name__ == "__main__":
    register()