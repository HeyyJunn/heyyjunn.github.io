---
title: "[CV] AlexNet: ImageNet Classification with Deep CNN"
date: 2026-09-14 03:27:08 +0900
last_modified_at: 2026-09-14 03:27:09 +0900
categories:
  - "Paper"
thumbnail:
  path: "/assets/img/velog/6545ba41-c62a-4dd0-bd0a-acd12767e755/6cd80002fd2410eaa2e8ded80206a40879e6c83dd4e41c24711438170df4b9b5.webp"
  alt: "[CV] AlexNet: ImageNet Classification with Deep CNN"
math: true
render_with_liquid: false
---
# Introduction
초기 객체 인식 분야는 머신러닝 기법에 주로 의존하였고, 성능 향상을 위해서 더 많은 양의 데이터셋, 더 깊은 모델, 과적합을 방지하기 위한 고도화된 학습 기법이 필요하게 되었음.

CNN은 FFN보다 더 적은 파라미터와 복잡성으로 학습하기 쉬움에도 불구하고 성능차이가 적다는 장점이 있지만, 고해상도와 같은 이미지에 대해서는 비용이 많이 들어감.

기존의 얕은 CNN 으로는 큰 모델을 학습하기에는 충분하지 않았기에, 더 깊은 구조를 가진 모델을 필요로 함.

그 당시 GPU의 발전으로 인해 최적화된 2d convlution 연산을 병렬 처리할 수 있게되어 깊은 모델을 구현할 수 있게 됨. 

**ReLU activation function, GPU 병렬처리, Drop-out, 데이터 증강** 등 당시 기준으로 혁신적인 구성 요소들을 효과적으로 통합했다는 것에 의의가 있음.

![](/assets/img/velog/6545ba41-c62a-4dd0-bd0a-acd12767e755/578e72fdd6b2e3d2261ed677ff3ac6a6694353cf1e63b0f42b8e535f733a7c8c.png)


# Dataset
## ImageNet Overview
![](/assets/img/velog/6545ba41-c62a-4dd0-bd0a-acd12767e755/219770e8bf806e639b24c2a38d3f78c3a33ab4e8c6826e2cc3cab018bcfde7c4.png)

ImageNet Dataset 은 2만2천개의 카테고리가 있는 150만개의 고해상도 이미지임.

120만개의 train dataset, 5만개의 validation dataset, 15만개의 test dataset을 제공함.

## Data pre-processing
- 256 x 256 고정된 크기로 맞춰 모델에 입력함
- 256 x 256 의 저강삭형 이미지를 얻기 위해 rescale한 사진의 center만 crop하여 이미지를 구축함
- 각 픽셀의 RGB 값을 전체 이미지의 RGB 평균으로 빼 정규화된 입력을 사용함

# Architecture
## ReLU Nonlinearity
### Limitations of Traditional Activation Functions
전통적인  tanh(x) 나 sigmoid 함수와 같은 activation function 들은 입력의 절댓값이 크면, gradient가 0으로 수렴하게 됨.

이로 인하여 학습속도가 느려지게 되고, gradient vanishing 문제가 발생함.

큰 입력값에 대한 대부분의 출력이 위와 같이 포화(saturating, 기울기가 0으로 수렴)구간에 머물게 됨.

### ReLU (Rectified Linear Unit)
ReLU(Rectified Linear Unit) 함수는 인공신경망에서 입력값이 0보다 크면 그대로 출력하고 0 이하면 0을 출력하는 활성화 함수임.

saturating한 활성화함수를 사용하는 것보다 ReLU와 같은 non-saturating한 활성화함수를 사용하는 것이 학습속도 측면에서 매우 빠름. 

![](/assets/img/velog/6545ba41-c62a-4dd0-bd0a-acd12767e755/a63c1c2ffe0798452ecb6851878ca5490aa27c625ce966848a08dea5cd7c0192.png)

ReLU(실선)을 사용하는 것이 6 epoch 으로 training error 25%에 도달했지만, tanh(점선)은 같은 수준에 도달하는데 38 epoch가 필요함을 볼 수 있음.

 ## Training on Multiple GPUs

저자들이 학습에서 사용한 GPU는 GTX580 으로 3GB 메모리 제한으로 인해 120만장의 이미지를 학습하기에 제약이 있어, **2개의 GPU를 병렬로 학습하여** 학습을 수행함.

![](/assets/img/velog/6545ba41-c62a-4dd0-bd0a-acd12767e755/5f7aa003ed5b328311a116dc22f46851d01d778ffb263bc35143a17b15fc8cd7.png)


하나의 Conv Filter는 하나의 출력 feature map을 만듦.
예를 들어 Conv1에 필터가 96개 있으면, $224\times224\times3 \rightarrow 55\times55\times96$ 처럼 96개의 feature map이 생김.

Alexnet은 이 96개를 두 GPU에 나눠 병렬로 계산함.
- Conv2: 같은 GPU의 Conv1 feature map만 사용
- Conv3: 두 GPU의 Conv2 feature map 전부 사용
- Conv4: 같은 GPU의 Conv3 feature map만 사용
- Conv5: 같은 GPU의 Conv4 feature map만 사용
- FC: 다시 전체가 연결됨

```
                 입력 이미지
                     │
          ┌──────────┴──────────┐
          ↓                     ↓
        GPU 1                  GPU 2
      Conv1 절반              Conv1 절반
          │                     │
          ↓                     ↓
      Conv2 절반              Conv2 절반
          │                     │
          └────────┬────────────┘
                   │
            ★ Conv3에서 통신 ★
          두 GPU 정보를 모두 봄
                   │
          ┌────────┴────────┐
          ↓                 ↓
        GPU 1             GPU 2
       Conv3              Conv3
          │                 │
       Conv4              Conv4
          │                 │
       Conv5              Conv5
          │                 │
          └───────┬─────────┘
                  ↓
              FC layers
                  ↓
             1000 classes
```

## LRN (Local Response Normalization) 
![](/assets/img/velog/6545ba41-c62a-4dd0-bd0a-acd12767e755/aee705a49e6c651efce093839c1b878328b233a0bd97189d10350db2ff060648.png)

LRN: 모델이 과도하게 특정 뉴런에 의존하지 않도록, 이웃 채널의 출력값을 기반으로 정규화하는 기법임. 즉, 같은 위치에서 여러 채널의 뉴런들이 너무 크게 활성화되면, 서로 경쟁시키는 정규화임.

(당시에는 ReLU의 결과값이 너무 커져서 주변 뉴런에 영향을 주는 것을 방지하기 위해 정규화 기법이 필요하였음.)

예를 들어 Conv를 통과한 뒤 같은 위치에서 5개 채널의 ReLU 출력이 $[1,\;2,\;\boxed{20},\;3,\;1]$ 이라고 하자.

가운데 채널 하나만 20으로 엄청 크다. LRN은 이 20을 그대로 두지 않고, 주변 채널들의 값까지 같이 보고

$20 \rightarrow \frac{20}{\text{주변 채널들의 활성화 크기를 반영한 값}}$ 처럼 큰 값을 억제함.

**ReLU는 음수를 제거하지만 양수의 활성화를 정규화하지 않기 때문에 이러한 LRN이 일반화에 도움을 줌.)**

결과: Top-1 error 1.4%, Top-5 error 1.2%만큼 감소함.

## Overlapping Pooling
### Concepts and Background
CNN에서 Pooling Layer는 공간적 해상도의 축소 및 불변성 확보를 위한 필수 구조임.

전통적 Pooling Layer는 stride S와 window Z를 동일하게 설정함.

논문의 저자들은 **stride < window 조건을 도입하여 겹치도록 pooling을 수행**함.

Overlapping Pooling 연산을 수행: Top-1 error 0.4%, Top-5 error 0.3% 감소. (stride=2, kernel=3x3 사용)

## Overall Architecture 
![](/assets/img/velog/6545ba41-c62a-4dd0-bd0a-acd12767e755/09d1f1dca30346b90e7a3859e8cc53a0728ed99e5d770e1c03ee12a875f90b07.png)

8개의 Layer로 구성됨.
- 5개의 Convolution Layers
- 3개의 Fully Connected Layers
