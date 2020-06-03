import traceback

import cv2
import numpy as np

from core import imagelib
from facelib import FaceType, LandmarksProcessor
from core.interact import interact as io
from core.cv2ex import *

def MergeMaskedFace (predictor_func, predictor_input_shape, cfg, frame_info, img_bgr_uint8, img_bgr, img_face_landmarks):
    img_size = img_bgr.shape[1], img_bgr.shape[0]
    img_face_mask_a = LandmarksProcessor.get_image_hull_mask (img_bgr.shape, img_face_landmarks)

    if cfg.mode == 'original':
        return img_bgr, img_face_mask_a

    out_img = img_bgr.copy()
    out_merging_mask_a = None

    input_size = predictor_input_shape[0]
    mask_subres_size = input_size*4
    output_size = input_size
    if cfg.super_resolution_power != 0:
        output_size *= 4

    face_mat        = LandmarksProcessor.get_transform_mat (img_face_landmarks, output_size, face_type=cfg.face_type)
    face_output_mat = LandmarksProcessor.get_transform_mat (img_face_landmarks, output_size, face_type=cfg.face_type, scale= 1.0 + 0.01*cfg.output_face_scale)

    if mask_subres_size == output_size:
        face_mask_output_mat = face_output_mat
    else:
        face_mask_output_mat = LandmarksProcessor.get_transform_mat (img_face_landmarks, mask_subres_size, face_type=cfg.face_type, scale= 1.0 + 0.01*cfg.output_face_scale)

    dst_face_bgr      = cv2.warpAffine( img_bgr        , face_mat, (output_size, output_size), flags=cv2.INTER_CUBIC )
    dst_face_bgr      = np.clip(dst_face_bgr, 0, 1)

    dst_face_mask_a_0 = cv2.warpAffine( img_face_mask_a, face_mat, (output_size, output_size), flags=cv2.INTER_CUBIC )
    dst_face_mask_a_0 = np.clip(dst_face_mask_a_0, 0, 1)

    predictor_input_bgr      = cv2.resize (dst_face_bgr, (input_size,input_size) )

    predicted = predictor_func (predictor_input_bgr)
    if isinstance(predicted, tuple):
        #merger return bgr,mask
        prd_face_bgr      = np.clip (predicted[0], 0, 1.0)
        prd_face_mask_a_0 = np.clip (predicted[1], 0, 1.0)
        predictor_masked = True
    else:
        #merger return bgr only, using dst mask
        prd_face_bgr      = np.clip (predicted, 0, 1.0 )
        prd_face_mask_a_0 = cv2.resize (dst_face_mask_a_0, (input_size,input_size) )
        predictor_masked = False

    if cfg.super_resolution_power != 0:
        prd_face_bgr_enhanced = cfg.superres_func(prd_face_bgr)
        mod = cfg.super_resolution_power / 100.0
        prd_face_bgr = cv2.resize(prd_face_bgr, (output_size,output_size))*(1.0-mod) + prd_face_bgr_enhanced*mod
        prd_face_bgr = np.clip(prd_face_bgr, 0, 1)

    if cfg.super_resolution_power != 0:
        if predictor_masked:
            prd_face_mask_a_0 = cv2.resize (prd_face_mask_a_0,  (output_size, output_size), cv2.INTER_CUBIC)
        else:
            prd_face_mask_a_0 = cv2.resize (dst_face_mask_a_0,  (output_size, output_size), cv2.INTER_CUBIC)

    if cfg.mask_mode == 2: #dst
        prd_face_mask_a_0 = cv2.resize (dst_face_mask_a_0, (output_size,output_size), cv2.INTER_CUBIC)
    elif cfg.mask_mode >= 3 and cfg.mask_mode <= 8:

        if cfg.mask_mode == 3 or cfg.mask_mode == 5 or cfg.mask_mode == 6:
            prd_face_fanseg_bgr = cv2.resize (prd_face_bgr, (cfg.fanseg_input_size,)*2 )
            prd_face_fanseg_mask = cfg.fanseg_extract_func(FaceType.FULL, prd_face_fanseg_bgr)
            FAN_prd_face_mask_a_0 = cv2.resize ( prd_face_fanseg_mask, (output_size, output_size), cv2.INTER_CUBIC)

        if cfg.mask_mode >= 4 and cfg.mask_mode <= 7:

            full_face_fanseg_mat = LandmarksProcessor.get_transform_mat (img_face_landmarks, cfg.fanseg_input_size, face_type=FaceType.FULL)
            dst_face_fanseg_bgr = cv2.warpAffine(img_bgr, full_face_fanseg_mat, (cfg.fanseg_input_size,)*2, flags=cv2.INTER_CUBIC )
            dst_face_fanseg_mask = cfg.fanseg_extract_func( FaceType.FULL, dst_face_fanseg_bgr )

            if cfg.face_type == FaceType.FULL:
                FAN_dst_face_mask_a_0 = cv2.resize (dst_face_fanseg_mask, (output_size,output_size), cv2.INTER_CUBIC)
            else:
                face_fanseg_mat = LandmarksProcessor.get_transform_mat (img_face_landmarks, cfg.fanseg_input_size, face_type=cfg.face_type)

                fanseg_rect_corner_pts = np.array ( [ [0,0], [cfg.fanseg_input_size-1,0], [0,cfg.fanseg_input_size-1] ], dtype=np.float32 )
                a = LandmarksProcessor.transform_points (fanseg_rect_corner_pts, face_fanseg_mat, invert=True )
                b = LandmarksProcessor.transform_points (a, full_face_fanseg_mat )
                m = cv2.getAffineTransform(b, fanseg_rect_corner_pts)
                FAN_dst_face_mask_a_0 = cv2.warpAffine(dst_face_fanseg_mask, m, (cfg.fanseg_input_size,)*2, flags=cv2.INTER_CUBIC )
                FAN_dst_face_mask_a_0 = cv2.resize (FAN_dst_face_mask_a_0, (output_size,output_size), cv2.INTER_CUBIC)

        if cfg.mask_mode == 3:   #FAN-prd
            prd_face_mask_a_0 = FAN_prd_face_mask_a_0
        elif cfg.mask_mode == 4: #FAN-dst
            prd_face_mask_a_0 = FAN_dst_face_mask_a_0
        elif cfg.mask_mode == 5:
            prd_face_mask_a_0 = FAN_prd_face_mask_a_0 * FAN_dst_face_mask_a_0
        elif cfg.mask_mode == 6:
            prd_face_mask_a_0 = prd_face_mask_a_0 * FAN_prd_face_mask_a_0 * FAN_dst_face_mask_a_0
        elif cfg.mask_mode == 7:
            prd_face_mask_a_0 = prd_face_mask_a_0 * FAN_dst_face_mask_a_0

    prd_face_mask_a_0[ prd_face_mask_a_0 < (1.0/255.0) ] = 0.0 # get rid of noise

    # resize to mask_subres_size
    if prd_face_mask_a_0.shape[0] != mask_subres_size:
        prd_face_mask_a_0 = cv2.resize (prd_face_mask_a_0, (mask_subres_size, mask_subres_size), cv2.INTER_CUBIC)

    # process mask in local predicted space
    if 'raw' not in cfg.mode:
        # add zero pad
        prd_face_mask_a_0 = np.pad (prd_face_mask_a_0, input_size)

        ero  = cfg.erode_mask_modifier
        blur = cfg.blur_mask_modifier

        if ero > 0:
            prd_face_mask_a_0 = cv2.erode(prd_face_mask_a_0, cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(ero,ero)), iterations = 1 )
        elif ero < 0:
            prd_face_mask_a_0 = cv2.dilate(prd_face_mask_a_0, cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(-ero,-ero)), iterations = 1 )

        # clip eroded/dilated mask in actual predict area
        # pad with half blur size in order to accuratelly fade to zero at the boundary
        clip_size = input_size + blur // 2

        prd_face_mask_a_0[:clip_size,:] = 0
        prd_face_mask_a_0[-clip_size:,:] = 0
        prd_face_mask_a_0[:,:clip_size] = 0
        prd_face_mask_a_0[:,-clip_size:] = 0

        if blur > 0:
            blur = blur + (1-blur % 2)
            prd_face_mask_a_0 = cv2.GaussianBlur(prd_face_mask_a_0, (blur, blur) , 0)

        prd_face_mask_a_0 = prd_face_mask_a_0[input_size:-input_size,input_size:-input_size]

        prd_face_mask_a_0 = np.clip(prd_face_mask_a_0, 0, 1)

    img_face_mask_a = cv2.warpAffine( prd_face_mask_a_0, face_mask_output_mat, img_size, np.zeros(img_bgr.shape[0:2], dtype=np.float32), flags=cv2.WARP_INVERSE_MAP | cv2.INTER_CUBIC )[...,None]
    img_face_mask_a = np.clip (img_face_mask_a, 0.0, 1.0)

    img_face_mask_a [ img_face_mask_a < (1.0/255.0) ] = 0.0 # get rid of noise

    if prd_face_mask_a_0.shape[0] != output_size:
        prd_face_mask_a_0 = cv2.resize (prd_face_mask_a_0, (output_size,output_size), cv2.INTER_CUBIC)

    prd_face_mask_a = prd_face_mask_a_0[...,None]
    prd_face_mask_area_a = prd_face_mask_a.copy()
    prd_face_mask_area_a[prd_face_mask_area_a>0] = 1.0

    if 'raw' in cfg.mode:
        if cfg.mode == 'raw-rgb':
            out_img = cv2.warpAffine( prd_face_bgr, face_output_mat, img_size, out_img, cv2.WARP_INVERSE_MAP | cv2.INTER_CUBIC, cv2.BORDER_TRANSPARENT )
            out_merging_mask_a = img_face_mask_a

        out_img = np.clip (out_img, 0.0, 1.0 )
    else:
        #averaging [lenx, leny, maskx, masky] by grayscale gradients of upscaled mask
        ar = []
        for i in range(1, 10):
            maxregion = np.argwhere( img_face_mask_a > i / 10.0 )
            if maxregion.size != 0:
                miny,minx = maxregion.min(axis=0)[:2]
                maxy,maxx = maxregion.max(axis=0)[:2]
                lenx = maxx - minx
                leny = maxy - miny
                if min(lenx,leny) >= 4:
                    ar += [ [ lenx, leny]  ]

        if len(ar) > 0:

            if 'seamless' not in cfg.mode and cfg.color_transfer_mode != 0:
                if cfg.color_transfer_mode == 1: #rct
                    prd_face_bgr = imagelib.reinhard_color_transfer ( np.clip( prd_face_bgr*prd_face_mask_area_a*255, 0, 255).astype(np.uint8),
                                                                      np.clip( dst_face_bgr*prd_face_mask_area_a*255, 0, 255).astype(np.uint8), )
                    
                    prd_face_bgr = np.clip( prd_face_bgr.astype(np.float32) / 255.0, 0.0, 1.0)
                elif cfg.color_transfer_mode == 2: #lct
                    prd_face_bgr = imagelib.linear_color_transfer (prd_face_bgr, dst_face_bgr)
                elif cfg.color_transfer_mode == 3: #mkl
                    prd_face_bgr = imagelib.color_transfer_mkl (prd_face_bgr, dst_face_bgr)
                elif cfg.color_transfer_mode == 4: #mkl-m
                    prd_face_bgr = imagelib.color_transfer_mkl (prd_face_bgr*prd_face_mask_area_a, dst_face_bgr*prd_face_mask_area_a)
                elif cfg.color_transfer_mode == 5: #idt
                    prd_face_bgr = imagelib.color_transfer_idt (prd_face_bgr, dst_face_bgr)
                elif cfg.color_transfer_mode == 6: #idt-m
                    prd_face_bgr = imagelib.color_transfer_idt (prd_face_bgr*prd_face_mask_area_a, dst_face_bgr*prd_face_mask_area_a)
                elif cfg.color_transfer_mode == 7: #sot-m
                    prd_face_bgr = imagelib.color_transfer_sot (prd_face_bgr*prd_face_mask_area_a, dst_face_bgr*prd_face_mask_area_a)
                    prd_face_bgr = np.clip (prd_face_bgr, 0.0, 1.0)
                elif cfg.color_transfer_mode == 8: #mix-m
                    prd_face_bgr = imagelib.color_transfer_mix (prd_face_bgr*prd_face_mask_area_a, dst_face_bgr*prd_face_mask_area_a)

            if cfg.mode == 'hist-match':
                hist_mask_a = np.ones ( prd_face_bgr.shape[:2] + (1,) , dtype=np.float32)

                if cfg.masked_hist_match:
                    hist_mask_a *= prd_face_mask_area_a

                white =  (1.0-hist_mask_a)* np.ones ( prd_face_bgr.shape[:2] + (1,) , dtype=np.float32)

                hist_match_1 = prd_face_bgr*hist_mask_a + white
                hist_match_1[ hist_match_1 > 1.0 ] = 1.0

                hist_match_2 = dst_face_bgr*hist_mask_a + white
                hist_match_2[ hist_match_1 > 1.0 ] = 1.0

                prd_face_bgr = imagelib.color_hist_match(hist_match_1, hist_match_2, cfg.hist_match_threshold ).astype(dtype=np.float32)

            if 'seamless' in cfg.mode:
                #mask used for cv2.seamlessClone
                img_face_seamless_mask_a = None
                for i in range(1,10):
                    a = img_face_mask_a > i / 10.0
                    if len(np.argwhere(a)) == 0:
                        continue
                    img_face_seamless_mask_a = img_face_mask_a.copy()
                    img_face_seamless_mask_a[a] = 1.0
                    img_face_seamless_mask_a[img_face_seamless_mask_a <= i / 10.0] = 0.0
                    break

            out_img = cv2.warpAffine( prd_face_bgr, face_output_mat, img_size, out_img, cv2.WARP_INVERSE_MAP | cv2.INTER_CUBIC, cv2.BORDER_TRANSPARENT )

            out_img = np.clip(out_img, 0.0, 1.0)

            if 'seamless' in cfg.mode:
                try:
                    #calc same bounding rect and center point as in cv2.seamlessClone to prevent jittering (not flickering)
                    l,t,w,h = cv2.boundingRect( (img_face_seamless_mask_a*255).astype(np.uint8) )
                    s_maskx, s_masky = int(l+w/2), int(t+h/2)
                    out_img = cv2.seamlessClone( (out_img*255).astype(np.uint8), img_bgr_uint8, (img_face_seamless_mask_a*255).astype(np.uint8), (s_maskx,s_masky) , cv2.NORMAL_CLONE )
                    out_img = out_img.astype(dtype=np.float32) / 255.0
                except Exception as e:
                    #seamlessClone may fail in some cases
                    e_str = traceback.format_exc()

                    if 'MemoryError' in e_str:
                        raise Exception("Seamless fail: " + e_str) #reraise MemoryError in order to reprocess this data by other processes
                    else:
                        print ("Seamless fail: " + e_str)


            out_img = img_bgr*(1-img_face_mask_a) + (out_img*img_face_mask_a)

            out_face_bgr = cv2.warpAffine( out_img, face_mat, (output_size, output_size), flags=cv2.INTER_CUBIC )

            if 'seamless' in cfg.mode and cfg.color_transfer_mode != 0:
                if cfg.color_transfer_mode == 1:
                    out_face_bgr = imagelib.reinhard_color_transfer ( np.clip(out_face_bgr*prd_face_mask_area_a*255, 0, 255).astype(np.uint8),
                                                                      np.clip(dst_face_bgr*prd_face_mask_area_a*255, 0, 255).astype(np.uint8) )
                    out_face_bgr = np.clip( out_face_bgr.astype(np.float32) / 255.0, 0.0, 1.0)
                elif cfg.color_transfer_mode == 2: #lct
                    out_face_bgr = imagelib.linear_color_transfer (out_face_bgr, dst_face_bgr)
                elif cfg.color_transfer_mode == 3: #mkl
                    out_face_bgr = imagelib.color_transfer_mkl (out_face_bgr, dst_face_bgr)
                elif cfg.color_transfer_mode == 4: #mkl-m
                    out_face_bgr = imagelib.color_transfer_mkl (out_face_bgr*prd_face_mask_area_a, dst_face_bgr*prd_face_mask_area_a)
                elif cfg.color_transfer_mode == 5: #idt
                    out_face_bgr = imagelib.color_transfer_idt (out_face_bgr, dst_face_bgr)
                elif cfg.color_transfer_mode == 6: #idt-m
                    out_face_bgr = imagelib.color_transfer_idt (out_face_bgr*prd_face_mask_area_a, dst_face_bgr*prd_face_mask_area_a)
                elif cfg.color_transfer_mode == 7: #sot-m
                    out_face_bgr = imagelib.color_transfer_sot (out_face_bgr*prd_face_mask_area_a, dst_face_bgr*prd_face_mask_area_a)
                    out_face_bgr = np.clip (out_face_bgr, 0.0, 1.0)
                elif cfg.color_transfer_mode == 8: #mix-m
                    out_face_bgr = imagelib.color_transfer_mix (out_face_bgr*prd_face_mask_area_a, dst_face_bgr*prd_face_mask_area_a)

            if cfg.mode == 'seamless-hist-match':
                out_face_bgr = imagelib.color_hist_match(out_face_bgr, dst_face_bgr, cfg.hist_match_threshold)

            cfg_mp = cfg.motion_blur_power / 100.0
            if cfg_mp != 0:
                k_size = int(frame_info.motion_power*cfg_mp)
                if k_size >= 1:
                    k_size = np.clip (k_size+1, 2, 50)
                    if cfg.super_resolution_power != 0:
                        k_size *= 2
                    out_face_bgr = imagelib.LinearMotionBlur (out_face_bgr, k_size , frame_info.motion_deg)

            if cfg.blursharpen_amount != 0:
                out_face_bgr = cfg.blursharpen_func ( out_face_bgr, cfg.sharpen_mode, 3, cfg.blursharpen_amount)


            if cfg.image_denoise_power != 0:
                n = cfg.image_denoise_power
                while n > 0:
                    img_bgr_denoised = cv2.medianBlur(img_bgr, 5)
                    if int(n / 100) != 0:
                        img_bgr = img_bgr_denoised
                    else:
                        pass_power = (n % 100) / 100.0
                        img_bgr = img_bgr*(1.0-pass_power)+img_bgr_denoised*pass_power
                    n = max(n-10,0)

            if cfg.bicubic_degrade_power != 0:
                p = 1.0 - cfg.bicubic_degrade_power / 101.0
                img_bgr_downscaled = cv2.resize (img_bgr, ( int(img_size[0]*p), int(img_size[1]*p ) ), cv2.INTER_CUBIC)
                img_bgr = cv2.resize (img_bgr_downscaled, img_size, cv2.INTER_CUBIC)

            new_out = cv2.warpAffine( out_face_bgr, face_mat, img_size, img_bgr.copy(), cv2.WARP_INVERSE_MAP | cv2.INTER_CUBIC, cv2.BORDER_TRANSPARENT )
            out_img =  np.clip( img_bgr*(1-img_face_mask_a) + (new_out*img_face_mask_a) , 0, 1.0 )

            if cfg.color_degrade_power != 0:
                out_img_reduced = imagelib.reduce_colors(out_img, 256)
                if cfg.color_degrade_power == 100:
                    out_img = out_img_reduced
                else:
                    alpha = cfg.color_degrade_power / 100.0
                    out_img = (out_img*(1.0-alpha) + out_img_reduced*alpha)

        out_merging_mask_a = img_face_mask_a

    return out_img, out_merging_mask_a


def MergeMasked (predictor_func, predictor_input_shape, cfg, frame_info):
    img_bgr_uint8 = cv2_imread(frame_info.filepath)
    img_bgr_uint8 = imagelib.normalize_channels (img_bgr_uint8, 3)
    img_bgr = img_bgr_uint8.astype(np.float32) / 255.0

    outs = []
    for face_num, img_landmarks in enumerate( frame_info.landmarks_list ):
        out_img, out_img_merging_mask = MergeMaskedFace (predictor_func, predictor_input_shape, cfg, frame_info, img_bgr_uint8, img_bgr, img_landmarks)
        outs += [ (out_img, out_img_merging_mask) ]

    #Combining multiple face outputs
    final_img = None
    final_mask = None
    for img, merging_mask in outs:
        h,w,c = img.shape

        if final_img is None:
            final_img = img
            final_mask = merging_mask
        else:
            final_img = final_img*(1-merging_mask) + img*merging_mask
            final_mask = np.clip (final_mask + merging_mask, 0, 1 )

    final_img = np.concatenate ( [final_img, final_mask], -1)

    return (final_img*255).astype(np.uint8)