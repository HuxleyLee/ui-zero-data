import av
import numpy as np
import cv2

# Local ANSI color constants for CLI output
_C_G = "\033[92m"  # green
_C_B = "\033[94m"  # blue
_C_N = "\033[0m"   # reset
_C_R = "\033[91m"  # red

class VideoFrameExtractor:
    def __init__(self, video_path):
        # 打开视频，只执行一次
        self.container = av.open(video_path)
        self.video_stream = self.container.streams.video[0]
        self.time_base = self.video_stream.time_base
        print(f"{_C_B}ℹ{_C_N} Video Frame Extractor established, time base: {self.time_base}")

    def extract_frame(self, target_second, save_path=None):
        """
        从当前视频对象中提取指定时间点的帧。
        """
        target_timestamp = int(target_second / self.time_base)
        self.container.seek(target_timestamp, stream=self.video_stream, backward=True, any_frame=False)

        for frame in self.container.decode(self.video_stream):
            if frame.time >= target_second:
                img = frame.to_rgb().to_ndarray()
                if save_path is not None:
                    # OpenCV expects BGR when writing; convert RGB -> BGR before saving
                    img_bgr = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
                    cv2.imwrite(save_path, img_bgr)
                    print(f"    {_C_G}✓{_C_N} 成功提取帧 @ {frame.time:.3f}s → {save_path}")
                # return the image as RGB ndarray (useful for downstream processing)
                return img
        print(f"    {_C_R}✗{_C_N} 未找到时间 {target_second}s 对应帧")
        return None

    def close(self):
        """手动关闭容器"""
        self.container.close()
        print("Extractor closed")




if __name__ == "__main__":
    video_path = "/data/lhx/LLaMA-Factory/data/demo/useit_data_engine/data/DO-QUOC-THAI_028-0006_0/video.mkv"
    target_second = 0.84
    save_path = "./test_frames/frame_at_0.84.jpg"
    extractor = VideoFrameExtractor(video_path)
    extractor.extract_frame(target_second, save_path)

    target_second = 5.03166
    save_path = "./test_frames/frame_at_5.03166.jpg"
    extractor.extract_frame(target_second, save_path)

    extractor.close()
