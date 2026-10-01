---
title: "[Paper] Vision Transformer: An Image is Worth 16x16 Words: Transformers for Image Recognition at Scale"
date: 2026-10-01 18:24:08 +0900
last_modified_at: 2026-10-01 19:28:46 +0900
categories:
  - "Paper"
math: true
render_with_liquid: false
---
# 1. Abstract

이미지를 고정 크기의 patch로 나누고, 각 patch를 token처럼 취급하여 standard Transformer를 이미지 분류에 직접 적용함.

ViT는 중간 규모의 데이터에서는 CNN보다 성능이 떨어질 수 있지만, 대규모 데이터셋으로 pre-training한 뒤 downstream task에 transfer하면 기존 CNN 기반 모델과 경쟁하거나 더 좋은 성능을 보임.

핵심적으로 CNN 없이도 Transformer만으로 image recognition이 가능하며, 데이터와 모델 규모가 커질수록 좋은 scalability를 보임.

# 2. Introduction

Transformer는 NLP에서 대규모 pre-training과 transfer learning을 통해 큰 성공을 거두었고, 이를 Vision에도 적용할 수 있는지 확인하고자 함.

기존 Vision 모델은 주로 CNN에 의존했지만, ViT는 이미지를 patch sequence로 변환하여 Transformer Encoder에 거의 그대로 입력함.

CNN에 비해 image-specific inductive bias가 적기 때문에 작은 데이터에서는 불리하지만, 충분히 큰 데이터로 학습하면 이러한 한계를 극복하고 강력한 representation learning 능력을 보임.

# 3. Method
## 3.1 Vision Transformer (ViT)
(필기로 대체함)
![](/assets/img/velog/6b656f86-cbf6-4450-bb30-f548fc4d9348/6aec18c4d97b393e7cda06823c4901ef87421882bab639dfdf90c0d607200082.jpg)

![](/assets/img/velog/6b656f86-cbf6-4450-bb30-f548fc4d9348/f9021ae2573b8976afcdabb3bf151ff41e2431eea004173815497449fa0d6994.jpg)


### Inductive bias.
핵심: CNN은 이미지의 2차원 구조를 구조적으로 알고 시작하지만, ViT는 거의 모른 채 시작한다 (CNN은 convolution 때문에 애초에 "가까이 붙어있는 픽셀 및 특징끼리 먼저 보자" 라는 구조가 강제로 내장되어 있음. 반면 ViT의 self-attention 은 처음부터 모든 patch를 서로 볼 수 있음.)

```
- 가까운 픽셀/patch끼리 연관이 크다 → locality
- 이미지가 2D 격자 구조다 → 2D neighborhood
- 물체가 조금 이동해도 같은 특징으로 본다 → translation equivariance
```

논문에서는 CNN은 locality, two-dimensional neighborhood structure, translation equivariance 와 같은 inductive bias를 가지고 있지만, 

**ViT**는 MLP layers 에서만 국소적이고 translationally equivariant함 + self-attention 에서는 Global 함을 언급함. 

2D neighborhood는 1. 모델의 시작부분 에서 이미지 patch를 나눌 때 2. fine-tuning 과정에서 서로 다른 해상도의 이미지에 맞게 position embedding을 조정할 때만 사용됨.

```
처음 patch를 자를 때
- 이미지를 16×16 같은 2D 블록으로 나눔
- 여기서만 이미지가 2차원 격자라는 사실을 직접 사용함

fine-tuning 때 해상도가 바뀌면 position embedding을 2D interpolation할 때
- 예: 224×224로 pretrain → 384×384로 fine-tuning
- patch 개수가 달라지니까 기존 position embedding을 2D 격자 기준으로 늘려 맞춤
```

### Hybrid Architecture.
raw image를 바로 patch로 만드는 대신 CNN feature map을 token으로 만들어 Transformer에 넣는 방식을 사용할 수 있음을 언급함.

## 3.2 Fine-Tuning and Higher Resolution
pre-train은 large datasets으로 하였고, fine-tune은 더 작은 downstream tasks로 진행함. 

pre-train 때 사용했던 prediction head를 제거하고, 0으로 초기화된 D x K 크기의 feedforward layer를 새로 붙임. (K=downstream task의 class 개수)

fine-tuning 에서는 더 높은 해상도의 이미지를 입력하게 되는데, 이때 patch size는 그대로 유지됨 $$\rightarrow$$ 이미지 안의 patch 개수가 늘어남 $$\rightarrow$$ pre-training 때 학습했던 PE이 더 이상 새로운 해상도에 적절하지 않을 수 있음 $$\rightarrow$$ 따라서 원본 이미지에서 각 patch가 있던 위치를 기준으로 사전학습된 position embedding에 2D interpolation을 수행함.

❓**Prediction head**: 모델이 만든 feature를 최종 class 점수로 바꾸는 마지막 분류층. 

$$
\text{[CLS]\ feature}\;(D)
\rightarrow
\mathrm{Linear}(D \rightarrow K)
\rightarrow
K\ \mathrm{class\ scores}
$$

# 4. Experiments
ResNet, Vision Transformer(ViT), 그리고 hybrid 모델의 representation learning 능력을 평가함. 각 모델이 어느 정도의 데이터를 필요로 하는지 이해하기 위해 서로 다른 크기의 데이터셋으로 사전학습한 뒤 다양한 benchmark task에서 평가했다고 밝힘.

사전학습 계산 비용 고려 시 매우 좋은 성능을 보였고, 더 낮은 사전학습 비용으로 대부분의 recognition benchmark 에서 SOTA.

마지막으로 self-supervision 을 이용한 작은 실험을 수행하여, 이 역시도 향후 발전 가능성이 있음을 시사함. (원래는 human supervision supervised learning)

❓**self-supervision**: 사람이 정답 라벨을 직접 붙여주지 않아도, 데이터 자체에서 학습용 정답을 만들어서 학습하는 방식.

## 4.1 Setup
### Datasets
**Pre-training용**
ILSVRC-2012 ImageNet: 1,000개 class, 130만 장 (개, 고양이, 자동차, 음식, 생활용품 등 일반적인 객체 이미지)
ImageNet-21k: 21,000개 class, 1,400만 장 (ImageNet-1k를 훨씬 확장한 데이터. 훨씬 다양한 사물·동물·개념 포함)
JFT: 18,000개 class, 3억 300만 장의 고해상도 이미지 (Google이 구축한 초대규모 이미지 데이터셋. 다양한 실제 이미지와 다중 라벨 포함)

**Transfer용**
ImageNet (동물, 사물 등 일반 이미지)
ImageNet-ReaL (ImageNet validation set의 라벨을 더 정확하게 재검토한 버전)
CIFAR-10/100 ($$32\times32$$ 저해상도 이미지. 자동차, 개, 고양이 등, CIFAR-10보다 세분화된 100종류 분류)
Oxford-IIIT Pets (개·고양이 품종 분류)
Oxford Flowers-102 (꽃 종류 분류)
등의 benchmark task로 transfer함.

pre-training data를 점점 크게 만들었을 때 ViT의 성능이 어떻게 scailing 되는가를 보고자 함. (모델 크기나 연산량을 키웠을 때 성능이 얼마나 잘 따라 올라가는지 보고자)

❓**de-duplicate**: downstream test image가 pre-training dataset에 우연히 들어가 있는 것을 제거한다는 뜻

또한 19개의 task로 구성된 VTAB classification suite에서도 모델을 평가. VTAB은 각 task마다 단 1,000개의 training example만 사용하며, 적은 데이터 환경에서 다양한 task로 transfer 하는 능력을 평가함. (적은 데이터만 가지고 새로운 문제에 얼마나 잘 적응하냐를 평가하는 benchmark임)

```
Natural
Pets, CIFAR 등 일반적인 자연 이미지 관련 task

Specialized
의료 영상이나 위성 영상처럼 특정 분야에 특화된 이미지 task

Structured
localization처럼 이미지의 위치나 기하학적 구조를 이해해야 하는 task
```

### Model Variants
![](/assets/img/velog/6b656f86-cbf6-4450-bb30-f548fc4d9348/f62e4c5a01217805520ee821d0f39fbd44f84bb09ac257fecea8f43390d73d47.png)

ViT configuration은 BERT에서 사용된 모델 configuration을 기반으로 함.

Vit-Base,Large 는 BERT의 모델 크기를 직접 가져옴. 거기에 더 큰 Huge 모델을 추가함.

Baseline 으로는 CNN을 사용하고 ResNet을 사용하지만, Batch Normalization layers를 Group Normalization으로 대체하고 standardized convolution (=convolution filter의 weight를 표준화한 뒤 convolution을 수행하는 방식을 말함)을 사용함. transfer learning 성능을 향상시키는 변경임.

Hybrid 모델에서는 CNN의 intermediate feature map을 ViT에 입력하고, 이때 CNN feature map에서 하나의 pixel을 하나의 patch처럼 취급함. 

### Training & Fine-tuning
#### In Pre-training,
모든 모델을 Adam optimizer로 학습하였음. 
(세부 hyperparameter 설정은 작성 생략)
Learning Rate Linear Warmup 과 Learning Rate decay를 사용함. (learning rate는 한번 업데이트 할 때 얼마나 크게 움직일지 정하는지의 개념으로서, 초반에는 LR을 선형적으로 올리고, 이후에는 선형적으로 줄였다.)

❓**Adam**: gradient의 방향과 크기를 함께 추적하면서 각 parameter의 learning rate를 자동 조절.
❓**Weight decay**: 모델이 학습하면서 weight 값이 지나치게 커지는 것을 억제하는 regularization

$$
L_{\text{total}} = L(w) + \lambda \|w\|^2
$$ 
에서 $$\lambda$$ 에 해당하는 개념. 

#### In Fine-tuning,
SGD with momentum optimizer를 사용함. batch size = 512.
Fine-tuning 시에는, pre-training 때보다 더 큰 크기의 이미지를 넣어서 fine-tuning 함. 

예를 들어, ViT-L/16 에서는 Pre-training: 224 x 224 $$\rightarrow$$ Fine-tuning: 512 x 512 로 입력 이미지의 해상도를 높임.

❓**SGD+Momentum VS. Adam**(헷갈렸던 부분)
**SGD + Momentum**: 과거 gradient의 방향을 누적해서 관성 있게 이동한다.
**Adam**: 방향도 누적하면서, gradient의 크기까지 추적해서 각 parameter마다 업데이트 크기를 자동 조절한다.
