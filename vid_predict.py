import cv2
import numpy as np
from PIL import Image

import colorsys
import os

import numpy as np
import torch
import torch.nn as nn
from PIL import ImageDraw, ImageFont

from nets.Network import Network

from utils.utils import (cvtColor, get_classes, preprocess_input, resize_image, show_config)
from utils.utils_bbox import decode_outputs, non_max_suppression
import glob


num_frame = 8
class Pred_vid(object):
    _defaults = {
        #--------------------------------------------------------------------------#
        #   使用自己训练好的模型进行预测一定要修改model_path和classes_path！
        #   model_path指向logs文件夹下的权值文件，classes_path指向model_data下的txt
        #
        #   训练好后logs文件夹下存在多个权值文件，选择验证集损失较低的即可。
        #   验证集损失较低不代表mAP较高，仅代表该权值在验证集上泛化性能较好。
        #   如果出现shape不匹配，同时要注意训练时的model_path和classes_path参数的修改
        #--------------------------------------------------------------------------#
        "model_path"        : '/data/luodengyan/code/我的红外/视频/循环/test20_加损失函数/logs_DAUB/2024_05_31_08_14_11/ep005-loss9.681-val_loss8.851.pth',   # 0.9785       Precision: 0.9930, Recall: 0.9931, F1: 0.9930  cost of time:87.05s
        "model_path"        : '/data/luodengyan/code/我的红外/视频/循环/test20_加损失函数/logs_IRDST_no_no/2024_06_01_08_14_16/ep008-loss12.878-val_loss16.862.pth',  # 0.9260 Precision: 0.9669, Recall: 0.9673, F1: 0.9671  cost of time:363.11s


        
        "classes_path"      : 'model_data/classes.txt',
        #---------------------------------------------------------------------#
        #   输入图片的大小，必须为32的倍数。
        #---------------------------------------------------------------------#
        "input_shape"       : [544, 544],
        #---------------------------------------------------------------------#
        #   所使用的YoloX的版本。nano、tiny、s、m、l、x
        #---------------------------------------------------------------------#
        "phi"               : 's',
        #---------------------------------------------------------------------#
        #   只有得分大于置信度的预测框会被保留下来
        #---------------------------------------------------------------------#
        "confidence"        : 0.5,
        #---------------------------------------------------------------------#
        #   非极大抑制所用到的nms_iou大小
        #---------------------------------------------------------------------#
        "nms_iou"           : 0.3,
        #---------------------------------------------------------------------#
        #   该变量用于控制是否使用letterbox_image对输入图像进行不失真的resize，
        #   在多次测试后，发现关闭letterbox_image直接resize的效果更好
        #---------------------------------------------------------------------#
        "letterbox_image"   : True,
        #-------------------------------#
        #   是否使用Cuda
        #   没有GPU可以设置成False
        #-------------------------------#
        "cuda"              : True,
    }

    @classmethod
    def get_defaults(cls, n):
        if n in cls._defaults:
            return cls._defaults[n]
        else:
            return "Unrecognized attribute name '" + n + "'"

    #---------------------------------------------------#
    #   初始化
    #---------------------------------------------------#
    def __init__(self, **kwargs):
        self.__dict__.update(self._defaults)
        for name, value in kwargs.items():
            setattr(self, name, value)
            
        #---------------------------------------------------#
        #   获得种类和先验框的数量
        #---------------------------------------------------#
        self.class_names, self.num_classes  = get_classes(self.classes_path)

        #---------------------------------------------------#
        #   画框设置不同的颜色
        #---------------------------------------------------#
        hsv_tuples = [(x / self.num_classes, 1., 1.) for x in range(self.num_classes)]
        self.colors = list(map(lambda x: colorsys.hsv_to_rgb(*x), hsv_tuples))
        self.colors = list(map(lambda x: (int(x[0] * 255), int(x[1] * 255), int(x[2] * 255)), self.colors))
        self.generate()
        
        show_config(**self._defaults)

    #---------------------------------------------------#
    #   生成模型
    #---------------------------------------------------#
    def generate(self, onnx=False):
        self.net    = Network(self.num_classes, num_frame=num_frame)
        device      = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        self.net.load_state_dict(torch.load(self.model_path, map_location=device))
        self.net    = self.net.eval()
        print('{} model, and classes loaded.'.format(self.model_path))
        if not onnx:
            if self.cuda:
                self.net = nn.DataParallel(self.net)
                self.net = self.net.cuda()
                
     #---------------------------------------------------#
    #   检测图片
    #---------------------------------------------------#
    def detect_image(self, images, position, crop = False, count = False):
        c_image = images[position]  # 中心目标图像

        #---------------------------------------------------#
        #   计算输入图片的高和宽
        #---------------------------------------------------#
        image_shape = np.array(np.shape(images[0])[0:2])

        #---------------------------------------------------------#
        #   在这里将图像转换成RGB图像，防止灰度图在预测时报错。
        #   代码仅仅支持RGB图像的预测，所有其它类型的图像都会转化成RGB
        #---------------------------------------------------------#
        images       = [cvtColor(image) for image in images]
        
        #---------------------------------------------------------#
        #   给图像增加灰条，实现不失真的resize
        #   也可以直接resize进行识别
        #---------------------------------------------------------#
        image_data  = [resize_image(image, (self.input_shape[1],self.input_shape[0]), self.letterbox_image) for image in images]
        image_data = [np.transpose(preprocess_input(np.array(image, dtype='float32')), (2, 0, 1)) for image in image_data]
        # (3, 640, 640) -> (3, 16, 640, 640)
        image_data = np.stack(image_data, axis=1)
        #---------------------------------------------------------#
        #   添加上batch_size维度
        #---------------------------------------------------------#
        image_data  = np.expand_dims(image_data, 0)

        with torch.no_grad():
            images = torch.from_numpy(image_data)
            if self.cuda:
                images = images.cuda()
            #---------------------------------------------------------#
            #   将图像输入网络当中进行预测！
            #---------------------------------------------------------#

            outputs_list = self.net(images)  # b, num_frame, 6, h, w
            outputs = [outputs_list[:, position, :, :, :]]

            outputs = decode_outputs(outputs, self.input_shape)

            #---------------------------------------------------------#
            #   将预测框进行堆叠，然后进行非极大抑制
            #---------------------------------------------------------#
            outputs = non_max_suppression(outputs, self.num_classes, self.input_shape, image_shape, self.letterbox_image, conf_thres = self.confidence, nms_thres = self.nms_iou)
      

            if outputs[0] is None: 
                return c_image

            top_label   = np.array(outputs[0][:, 6], dtype = 'int32')
            top_conf    = outputs[0][:, 4] * outputs[0][:, 5]
            top_boxes   = outputs[0][:, :4]
            

        #---------------------------------------------------------#
        #   设置字体与边框厚度
        #---------------------------------------------------------#
        font        = ImageFont.truetype(font='model_data/simhei.ttf', size=np.floor(3e-2 * c_image.size[1] + 15).astype('int32'))  
        thickness   = int(max((c_image.size[0] + c_image.size[1]) // np.mean(self.input_shape), 1))
        thickness   = 1
        #---------------------------------------------------------#
        #   计数
        #---------------------------------------------------------#
        if count:
            print("top_label:", top_label)
            classes_nums    = np.zeros([self.num_classes])
            for i in range(self.num_classes):
                num = np.sum(top_label == i)
                if num > 0:
                    print(self.class_names[i], " : ", num)
                classes_nums[i] = num
            print("classes_nums:", classes_nums)
        #---------------------------------------------------------#
        #   是否进行目标的裁剪
        #---------------------------------------------------------#
        if crop:
            for i, c in list(enumerate(top_label)):
                top, left, bottom, right = top_boxes[i]
                
                top     = max(0, np.floor(top).astype('int32'))
                left    = max(0, np.floor(left).astype('int32'))
                bottom  = min(c_image.size[1], np.floor(bottom).astype('int32'))
                right   = min(c_image.size[0], np.floor(right).astype('int32'))
                
                dir_save_path = "img_crop"
                if not os.path.exists(dir_save_path):
                    os.makedirs(dir_save_path)
                crop_image = c_image.crop([left, top, right, bottom])
                crop_image.save(os.path.join(dir_save_path, "crop_" + str(i) + ".png"), quality=95, subsampling=0)
                print("save crop_" + str(i) + ".png to " + dir_save_path)



        #---------------------------------------------------------#
        #   图像绘制
        #---------------------------------------------------------#
        for i, c in list(enumerate(top_label)):
            predicted_class = self.class_names[int(c)]
            box             = top_boxes[i]
            score           = top_conf[i]


            # 真实: 98, 84, 106, 92
            # print(box)  # [ 84.00028   97.921875  92.167595 106.055115]
            # top, left, bottom, right = box


            # # 真实: 53,47,61,55
            # print(box)  # [ 88.70596  96.12964  96.785   104.16962]
            # top, left, bottom, right = box
            # # top, left, bottom, right = 47, 53, 55, 61


            # 真实: 346,332,352,339
            print(box)  # [ 88.70596  96.12964  96.785   104.16962]
            top, left, bottom, right = box
            # top, left, bottom, right = 47, 53, 55, 61




            # 真实: 420,290,427,297,0
            print(box)  # [ 88.70596  96.12964  96.785   104.16962]
            top, left, bottom, right = box
            # top, left, bottom, right = 290, 420, 297, 427



            top     = max(0, np.floor(top).astype('int32'))
            left    = max(0, np.floor(left).astype('int32'))
            bottom  = min(c_image.size[1], np.floor(bottom).astype('int32'))
            right   = min(c_image.size[0], np.floor(right).astype('int32'))

            label = '{} {:.2f}'.format(predicted_class, score)
            draw = ImageDraw.Draw(c_image)
            # label_size = draw.textsize(label, font)
            label_size = draw.textbbox((125, 20), label, font)
            label = label.encode('utf-8')
            # print(label, top, left, bottom, right)
            
            if top - label_size[1] >= 0:
                text_origin = np.array([left, top - label_size[1]])
            else:
                text_origin = np.array([left, top + 1])

            for i in range(thickness):
                draw.rectangle([left + i, top + i, right - i, bottom - i], outline=self.colors[c])

            # draw.rectangle([tuple(text_origin), tuple(text_origin + label_size[:2])], fill=self.colors[c])
            # draw.rectangle([tuple(text_origin), tuple(text_origin)], fill=self.colors[c])
            # draw.text(text_origin, str(label, 'UTF-8'), fill=(0, 0, 0), font=font)
            del draw
        return c_image


if __name__ == "__main__":
    """
    python vid_predict.py

    需要修改：
    "model_path"
    mode
    img

    "input_shape" 
    thickness   = 1
    """
    yolo = Pred_vid()
    #----------------------------------------------------------------------------------------------------------#
    #   mode用于指定测试的模式：
    #   'predict'           表示单张图片预测，如果想对预测过程进行修改，如保存图片，截取对象等，可以先看下方详细的注释
    #----------------------------------------------------------------------------------------------------------#
    # mode = "video"
    mode = "predict"
    #-------------------------------------------------------------------------#
    #   crop                指定了是否在单张图片预测后对目标进行截取
    #   count               指定了是否进行目标的计数
    #   crop、count仅在mode='predict'时有效
    #-------------------------------------------------------------------------#
    crop            = False
    count           = False
    #----------------------------------------------------------------------------------------------------------#
    if mode == "predict":
        # img = '/home/luodengyan/tmp/master-红外目标检测/视频/数据集/DAUB_csj/DAUB/images/test/data6/254.bmp'
        # img = '/home/luodengyan/tmp/master-红外目标检测/视频/数据集/DAUB_csj/DAUB/images/test/data15/15.bmp'


        img = '/home/luodengyan/tmp/master-红外目标检测/视频/数据集/IRDST_csj/images/8/789.bmp'
        # img = '/home/luodengyan/tmp/master-红外目标检测/视频/数据集/IRDST_csj/images/18/99.bmp'


        img_dir = os.path.dirname(img)
        frames_num = len(sorted(glob.glob(img_dir + '/*.bmp')))
        img_num = int(img.split('/')[-1].split('.')[0])  

        clip_list = [] 
        for i in range(0, frames_num, num_frame):
            frame_range = list(range(i, i+num_frame))
            frame_range = np.clip(frame_range, 0, frames_num-1)

            # 找到当前帧在哪个clip中
            if img_num in frame_range:
                for j in frame_range:
                    clip_list.append( os.path.join(img_dir, str(j) +'.bmp' ))
                
                # 检索当前帧在当前clip中的位置
                position = list(frame_range).index(img_num)  
                break
            

        images = [Image.open(item) for item in clip_list]
        r_image = yolo.detect_image(images, position, crop=crop, count=count)

        if not os.path.exists('save'):
            os.makedirs('save')

        img_name = img.split('/')[-2] + '-' + img.split('/')[-1].split('.')[0]
        r_image.save(f"./save/{img_name}-pred.png")
        # r_image.save(f"./save/{img_name}-gt.png")


        




    elif mode == "video":
        import numpy as np
        from tqdm import tqdm
        dir_path = '/home/luodengyan/tmp/master-红外目标检测/视频/数据集/DAUB_csj/DAUB/images/test/data6/'

        images = os.listdir(dir_path)
        images.sort(key=lambda x:int(x[:-4]))
        list_img = []

        for image in tqdm(images):
            image = dir_path+image
            img = get_history_imgs(image)
            imgs = [Image.open(item) for item in img]
            r_image = yolo.detect_image(imgs, crop = crop, count=count)
            print(cv2.cvtColor(np.asarray(r_image), cv2.COLOR_RGB2BGR).shape)
            exit(1)
            list_img.append(cv2.cvtColor(np.asarray(r_image), cv2.COLOR_RGB2BGR))  # cv2.cvtColor(np.asarray(r_image), cv2.COLOR_RGB2BGR): 
        
        fourcc = cv2.VideoWriter_fourcc(*'MJPG')# *'XVID'           视频编解码器
        outfile = cv2.VideoWriter("./output.avi", fourcc, 5, (256, 256), True)    #大小必须和图片大小一致,且所有图片大小必须一致   -- photo_resize.py      
        
        for i in list_img: 
            outfile.write(i) # 视频文件写入一帧
            #cv2.imshow('frame', next(img_iter)) 
            if cv2.waitKey(1) == 27: # 按下Esc键，程序退出(Esc的ASCII值是27，即0001  1011)
                break 
        outfile.release()
        cv2.destroyAllWindows()
    else:
        raise AssertionError("Please specify the correct mode: 'predict', 'video', 'fps', 'heatmap', 'export_onnx', 'dir_predict'.")