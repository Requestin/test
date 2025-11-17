#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os, re, time, sys
import numpy as np
from PIL import Image
import imageio
from tqdm import tqdm
import torch
from einops import rearrange

from diffsynth import ModelManager, FlashVSRFullPipeline
from utils.utils import Causal_LQ4x_Proj

def tensor2video(frames: torch.Tensor):
    frames = rearrange(frames, "C T H W -> T H W C")
    frames = ((frames.float() + 1) * 127.5).clip(0, 255).cpu().numpy().astype(np.uint8)
    frames = [Image.fromarray(frame) for frame in frames]
    return frames

def natural_key(name: str):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r'([0-9]+)', os.path.basename(name))]

def list_images_natural(folder: str):
    exts = ('.png', '.jpg', '.jpeg', '.PNG', '.JPG', '.JPEG')
    fs = [os.path.join(folder, f) for f in os.listdir(folder) if f.endswith(exts)]
    fs.sort(key=natural_key)
    return fs

def largest_8n1_leq(n):  # 8n+1
    return 0 if n < 1 else ((n - 1)//8)*8 + 1

def is_video(path): 
    return os.path.isfile(path) and path.lower().endswith(('.mp4','.mov','.avi','.mkv'))

def gather_inputs(root: str):
    if not os.path.isdir(root):
        return []
    entries = []
    for name in sorted(os.listdir(root), key=natural_key):
        path = os.path.join(root, name)
        if os.path.isdir(path):
            try:
                if list_images_natural(path):
                    entries.append(path)
            except Exception:
                continue
        elif is_video(path):
            entries.append(path)
    return entries

def pil_to_tensor_neg1_1(img: Image.Image, dtype=torch.bfloat16, device='cuda'):
    t = torch.from_numpy(np.asarray(img, np.uint8)).to(device=device, dtype=torch.float32)  # HWC
    t = t.permute(2,0,1) / 255.0 * 2.0 - 1.0                                              # CHW in [-1,1]
    return t.to(dtype)

def save_video(frames, save_path, fps=30, quality=5):
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    w = imageio.get_writer(save_path, fps=fps, quality=quality)
    for f in tqdm(frames, desc=f"Saving {os.path.basename(save_path)}"):
        w.append_data(np.array(f))
    w.close()

def compute_scaled_and_target_dims(
    w0: int,
    h0: int,
    scale: float = 4.0,
    max_w: int = 2560,
    max_h: int = 1440,
    multiple: int = 128,
):
    if w0 <= 0 or h0 <= 0:
        raise ValueError("invalid original size")

    scale_eff = min(scale, max_w / w0, max_h / h0)
    scale_eff = max(1.0, scale_eff)

    sW = int(round(w0 * scale_eff))
    sH = int(round(h0 * scale_eff))

    floor_w = max(multiple, (sW // multiple) * multiple)
    floor_h = max(multiple, (sH // multiple) * multiple)
    ceil_w = max(multiple, ((sW + multiple - 1) // multiple) * multiple)
    ceil_h = max(multiple, ((sH + multiple - 1) // multiple) * multiple)

    can_round_up = (ceil_w <= max_w) and (ceil_h <= max_h)
    if can_round_up:
        tW, tH = ceil_w, ceil_h
    else:
        tW, tH = min(floor_w, max_w), min(floor_h, max_h)

    return sW, sH, tW, tH, scale_eff

def upscale_then_center_crop(img: Image.Image, sW: int, sH: int, tW: int, tH: int) -> Image.Image:
    # 先放大
    up = img.resize((sW, sH), Image.BICUBIC)
    # 中心裁剪
    l = max(0, (sW - tW) // 2); t = max(0, (sH - tH) // 2)
    return up.crop((l, t, l + tW, t + tH))

def prepare_input_tensor(path: str, scale: int = 4, dtype=torch.bfloat16, device='cuda'):
    if os.path.isdir(path):
        paths0 = list_images_natural(path)
        if not paths0:
            raise FileNotFoundError(f"No images in {path}")
        with Image.open(paths0[0]) as _img0:
            w0, h0 = _img0.size
        N0 = len(paths0)
        print(f"[{os.path.basename(path)}] Original Resolution: {w0}x{h0} | Original Frames: {N0}")

        sW, sH, tW, tH, scale_eff = compute_scaled_and_target_dims(w0, h0, scale=scale, multiple=128)
        print(
            f"[{os.path.basename(path)}] Scaled Resolution (x{scale_eff:.2f}): "
            f"{sW}x{sH} -> Target (128-multiple): {tW}x{tH}"
        )

        paths = paths0 + [paths0[-1]] * 4
        F = largest_8n1_leq(len(paths))
        if F == 0:
            raise RuntimeError(f"Not enough frames after padding in {path}. Got {len(paths)}.")
        paths = paths[:F]
        print(f"[{os.path.basename(path)}] Target Frames (8n-3): {F-4}")

        frames = []
        for p in paths:
            with Image.open(p).convert('RGB') as img:
                img_out = upscale_then_center_crop(img, sW=sW, sH=sH, tW=tW, tH=tH)   
            frames.append(pil_to_tensor_neg1_1(img_out, dtype, device))             
        vid = torch.stack(frames, 0).permute(1,0,2,3).unsqueeze(0)             
        fps = 30
        return vid, tH, tW, F, fps

    if is_video(path):
        rdr = imageio.get_reader(path)
        first = Image.fromarray(rdr.get_data(0)).convert('RGB')
        w0, h0 = first.size

        meta = {}
        try:
            meta = rdr.get_meta_data()
        except Exception:
            pass
        fps_val = meta.get('fps', 30)
        fps = int(round(fps_val)) if isinstance(fps_val, (int, float)) else 30

        def count_frames(r):
            try:
                nf = meta.get('nframes', None)
                if isinstance(nf, int) and nf > 0:
                    return nf
            except Exception:
                pass
            try:
                return r.count_frames()
            except Exception:
                n = 0
                try:
                    while True:
                        r.get_data(n); n += 1
                except Exception:
                    return n

        total = count_frames(rdr)
        if total <= 0:
            rdr.close()
            raise RuntimeError(f"Cannot read frames from {path}")

        print(f"[{os.path.basename(path)}] Original Resolution: {w0}x{h0} | Original Frames: {total} | FPS: {fps}")

        sW, sH, tW, tH, scale_eff = compute_scaled_and_target_dims(w0, h0, scale=scale, multiple=128)
        print(
            f"[{os.path.basename(path)}] Scaled Resolution (x{scale_eff:.2f}): "
            f"{sW}x{sH} -> Target (128-multiple): {tW}x{tH}"
        )

        idx = list(range(total)) + [total - 1] * 4
        F = largest_8n1_leq(len(idx))
        if F == 0:
            rdr.close()
            raise RuntimeError(f"Not enough frames after padding in {path}. Got {len(idx)}.")
        idx = idx[:F]
        print(f"[{os.path.basename(path)}] Target Frames (8n-3): {F-4}")

        frames = []
        try:
            for i in idx:
                img = Image.fromarray(rdr.get_data(i)).convert('RGB')
                img_out = upscale_then_center_crop(img, sW=sW, sH=sH, tW=tW, tH=tH)
                frames.append(pil_to_tensor_neg1_1(img_out, dtype, device))
        finally:
            try:
                rdr.close()
            except Exception:
                pass

        vid = torch.stack(frames, 0).permute(1,0,2,3).unsqueeze(0)   # 1 C F H W
        return vid, tH, tW, F, fps

    raise ValueError(f"Unsupported input: {path}")

def init_pipeline():
    print(torch.cuda.current_device(), torch.cuda.get_device_name(torch.cuda.current_device()))
    mm = ModelManager(torch_dtype=torch.bfloat16, device="cpu")
    mm.load_models([
        "./FlashVSR-v1.1/diffusion_pytorch_model_streaming_dmd.safetensors",
        "./FlashVSR-v1.1/Wan2.1_VAE.pth",
    ])
    pipe = FlashVSRFullPipeline.from_model_manager(mm, device="cuda")
    pipe.denoising_model().LQ_proj_in = Causal_LQ4x_Proj(in_dim=3, out_dim=1536, layer_num=1).to("cuda", dtype=torch.bfloat16)
    LQ_proj_in_path = "./FlashVSR-v1.1/LQ_proj_in.ckpt"
    if os.path.exists(LQ_proj_in_path):
        pipe.denoising_model().LQ_proj_in.load_state_dict(torch.load(LQ_proj_in_path, map_location="cpu"), strict=True)

    pipe.denoising_model().LQ_proj_in.to('cuda')
    pipe.vae.model.encoder = None
    pipe.vae.model.conv1 = None
    pipe.to('cuda'); pipe.enable_vram_management(num_persistent_param_in_dit=None)
    pipe.init_cross_kv(); pipe.load_models_to_device(["dit","vae"])
    return pipe

def parse_cli_inputs(default_inputs):
    args = sys.argv[1:]
    if not args:
        return default_inputs

    parsed = []
    for raw in args:
        if raw in ("-h", "--help"):
            print(
                "Usage:\n"
                "  python infer_flashvsr_v1.1_full_modified.py [--video1.mp4 --video2.mp4 ...]\n"
                "Пример: python infer_flashvsr_v1.1_full_modified.py --example1000.mp4 --example1001.mp4\n"
                "Можно также указывать полный путь или относительный путь без префикса '--'."
            )
            sys.exit(0)

        entry = raw
        if entry.startswith("--"):
            entry = entry[2:]
        entry = entry.strip()
        if not entry:
            continue

        if not os.path.isabs(entry) and not os.path.exists(entry):
            candidate = os.path.join("./inputs", entry)
            if os.path.exists(candidate):
                entry = candidate

        parsed.append(entry)

    if not parsed:
        return default_inputs

    print("[CLI] Используем входные файлы:", parsed)
    return parsed

def main():
    RESULT_ROOT = "./results"
    os.makedirs(RESULT_ROOT, exist_ok=True)
    default_inputs = [
        #"./inputs/example1_part2_res720_5sec.mp4",
	#"./inputs/example1_part3_res720_9sec.mp4",
        "./inputs/example9.mp4",
        # "./inputs/example2.mp4",
        # "./inputs/example3.mp4",
    ]
    inputs = parse_cli_inputs(default_inputs)
    seed, scale, dtype, device = 0, 4, torch.bfloat16, 'cuda'
    sparse_ratio = 2.0      # Recommended: 1.5 or 2.0. 1.5 → faster; 2.0 → more stable.
    pipe = init_pipeline()

    for p in inputs:
        torch.cuda.empty_cache(); torch.cuda.ipc_collect()
        name = os.path.basename(p.rstrip('/'))
        if name.startswith('.'):
            continue
        try:
            LQ, th, tw, F, fps = prepare_input_tensor(p, scale=scale, dtype=dtype, device=device)
        except Exception as e:
            print(f"[Error] {name}: {e}")
            continue

        video = pipe(
            prompt="", negative_prompt="", cfg_scale=1.0, num_inference_steps=1, seed=seed, 
            tiled=False,# Disable tiling: faster inference but higher VRAM usage. 
                        # Set to True for lower memory consumption at the cost of speed.
            LQ_video=LQ, num_frames=F, height=th, width=tw, is_full_block=False, if_buffer=True,
            topk_ratio=sparse_ratio*768*1280/(th*tw), 
            kv_ratio=3.0,
            local_range=9, # Recommended: 9 or 11. local_range=9 → sharper details; 11 → more stable results.
            color_fix = True,
        )
        video = tensor2video(video)
        save_video(video, os.path.join(RESULT_ROOT, f"FlashVSR_v1.1_Full_{name.split('.')[0]}_seed{seed}.mp4"), fps=fps, quality=6)
    print("Done.")

if __name__ == "__main__":
    main()
