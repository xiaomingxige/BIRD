﻿
# *BIRD*
The PyTorch implementation for the BIRD: Bidirectional Temporal Information Propagation for Moving Infrared Dim-small Target Detection.
## 1. Pre-request
### 1.1. Environment
```bash
conda create -n BIRD python=3.10.11
conda activate BIRD
conda install pytorch==1.12.0 torchvision==0.13.0 torchaudio==0.12.0 cudatoolkit=11.3 -c pytorch

git clone --depth=1 https://github.com/xiaomingxige/BIRD
cd BIRD
pip install -r requirements.txt
```
### 1.2. DCNv2
#### Build DCNv2

```bash
cd nets/ops/dcn/
# You may need to modify the paths of cuda before compiling.
bash build.sh
```
#### Check if DCNv2 works (optional)

```bash
python simple_check.py
```
> The DCNv2 source files here is different from the [open-sourced version](https://github.com/chengdazhi/Deformable-Convolution-V2-PyTorch) due to incompatibility. [[issue]](https://github.com/open-mmlab/mmediting/issues/84#issuecomment-644974315)

### 1.3. Datasets
Please follow [SSTNet](https://github.com/UESTC-nnLab/SSTNet) to download the datasets.
## 2. Train
```bash
CUDA_VISIBLE_DEVICES=1 nohup python -u train.py > nohup.out &
```
> Please modify the corresponding file path in train.py before training.
## 3. Test
We utilize 1 NVIDIA GeForce RTX 3090 GPU for testing：

```bash
python vid_map_coco.py
```

## 4. Visualization
```bash
python vid_predict.py
```
## Acknowledgements
This work is based on [SSTNet](https://github.com/UESTC-nnLab/SSTNet). Thank [UESTC-nnLab](https://github.com/UESTC-nnLab) for sharing the codes.
