"""
Uzbek OCR Model — EasyOCR Integration Module
=============================================
This module defines the CRNN model architecture for EasyOCR inference.

The class is named ``Model`` so that EasyOCR's ``recog_network`` loader
can import it directly::

    recog_network='uzbek_model'
    # EasyOCR does: from uzbek_model import Model

Architecture:
    VGG Feature Extractor → BiLSTM × 2 → Linear prediction head

This file mirrors the exact architecture used in ``train_model.py`` so
that trained weights are directly compatible.
"""

from __future__ import annotations

import torch
import torch.nn as nn


# ===================================================================
# Building blocks
# ===================================================================


class VGG_FeatureExtractor(nn.Module):
    """
    VGG-like CNN for feature extraction.

    Input:  (batch, input_channel, 64, W) — grayscale or RGB images
    Output: (batch, output_channel, 1, W') — feature maps
    """

    def __init__(self, input_channel: int = 1, output_channel: int = 256) -> None:
        super().__init__()
        self.output_channel = [
            int(output_channel / 8),   # 32
            int(output_channel / 4),   # 64
            int(output_channel / 2),   # 128
            output_channel,            # 256
        ]

        self.conv_net = nn.Sequential(
            # Block 1
            nn.Conv2d(input_channel, self.output_channel[0], 3, 1, 1),
            nn.ReLU(True),
            nn.MaxPool2d(2, 2),

            # Block 2
            nn.Conv2d(self.output_channel[0], self.output_channel[1], 3, 1, 1),
            nn.ReLU(True),
            nn.MaxPool2d(2, 2),

            # Block 3
            nn.Conv2d(self.output_channel[1], self.output_channel[2], 3, 1, 1),
            nn.ReLU(True),
            nn.Conv2d(self.output_channel[2], self.output_channel[2], 3, 1, 1),
            nn.ReLU(True),
            nn.MaxPool2d((2, 1), (2, 1)),

            # Block 4
            nn.Conv2d(self.output_channel[2], self.output_channel[3], 3, 1, 1, bias=False),
            nn.BatchNorm2d(self.output_channel[3]),
            nn.ReLU(True),
            nn.Conv2d(self.output_channel[3], self.output_channel[3], 3, 1, 1, bias=False),
            nn.BatchNorm2d(self.output_channel[3]),
            nn.ReLU(True),
            nn.MaxPool2d((2, 1), (2, 1)),

            # Final squeeze
            nn.Conv2d(self.output_channel[3], self.output_channel[3], 2, (2, 1), (0, 1)),
            nn.ReLU(True),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.conv_net(x)


class BidirectionalLSTM(nn.Module):
    """
    BiLSTM for sequence modelling.

    Input:  (seq_len, batch, input_size)
    Output: (seq_len, batch, output_size)
    """

    def __init__(self, input_size: int, hidden_size: int, output_size: int) -> None:
        super().__init__()
        self.rnn = nn.LSTM(
            input_size, hidden_size, bidirectional=True, batch_first=False
        )
        self.linear = nn.Linear(hidden_size * 2, output_size)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        recurrent, _ = self.rnn(x)
        output = self.linear(recurrent)
        return output


# ===================================================================
# Main model class (EasyOCR expects the name "Model")
# ===================================================================


class Model(nn.Module):
    """
    CRNN model for text recognition.

    This is the same VGG → BiLSTM → CTC architecture used during training.
    EasyOCR loads this class by name when ``recog_network='uzbek_model'``.

    Args:
        input_channel:  Number of image channels (1 for grayscale).
        output_channel: Number of feature channels from the VGG extractor.
        hidden_size:    Hidden dimension of the BiLSTM layers.
        num_class:      Total number of output classes (charset + CTC blank).
    """

    def __init__(
        self,
        input_channel: int = 1,
        output_channel: int = 256,
        hidden_size: int = 256,
        num_class: int = 100,
    ) -> None:
        super().__init__()
        self.feature_extractor = VGG_FeatureExtractor(input_channel, output_channel)
        self.adaptive_pool = nn.AdaptiveAvgPool2d((1, None))

        self.sequence_model = nn.Sequential(
            BidirectionalLSTM(output_channel, hidden_size, hidden_size),
            BidirectionalLSTM(hidden_size, hidden_size, hidden_size),
        )
        self.prediction = nn.Linear(hidden_size, num_class)

    def forward(self, x: torch.Tensor, text: torch.Tensor | None = None) -> torch.Tensor:
        """
        Forward pass.

        Args:
            x: Input image tensor of shape ``(batch, C, H, W)``.
            text: Optional text tensor (ignored, for EasyOCR interface compatibility).

        Returns:
            Logits tensor of shape ``(batch, seq_len, num_class)`` as expected by EasyOCR.
        """
        # Undo EasyOCR's [-1, 1] normalization to match [0, 1] training normalization
        x = x * 0.5 + 0.5

        # Feature extraction
        visual = self.feature_extractor(x)  # (batch, output_channel, H', W')
        visual = self.adaptive_pool(visual)  # (batch, output_channel, 1, W')

        # Reshape: squeeze height, permute to sequence-first
        visual = visual.squeeze(2)              # (batch, C, W')
        visual = visual.permute(2, 0, 1)        # (W', batch, C) = (seq, batch, feat)

        # Sequence modelling
        contextual = self.sequence_model(visual)  # (seq, batch, hidden)

        # Prediction
        output = self.prediction(contextual)      # (seq, batch, num_class)
        
        # Permute to (batch, seq_len, num_class) for EasyOCR
        return output.permute(1, 0, 2)
