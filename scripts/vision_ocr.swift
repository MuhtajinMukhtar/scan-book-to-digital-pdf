// macOS Vision OCR CLI (built once into the per-book work directory).
// Usage: swiftc vision_ocr.swift -o vision_ocr_cli
//        ./vision_ocr_cli page_001.jpg id-ID,en-US
import Foundation
import Vision
import ImageIO

func fail(_ message: String, _ code: Int32 = 2) -> Never {
    fputs(message + "\n", stderr)
    exit(code)
}

guard CommandLine.arguments.count >= 3 else {
    fail("Usage: vision_ocr_cli input.jpg id-ID,en-US")
}
let fileURL = URL(fileURLWithPath: CommandLine.arguments[1])
let locales = CommandLine.arguments[2].split(separator: ",").map(String.init)
guard !locales.isEmpty else { fail("At least one locale is required") }
guard let source = CGImageSourceCreateWithURL(fileURL as CFURL, nil),
      let cg = CGImageSourceCreateImageAtIndex(source, 0, nil) else {
    fail("Could not read page raster image")
}

let request = VNRecognizeTextRequest()
request.recognitionLevel = .accurate
request.usesLanguageCorrection = true
request.recognitionLanguages = locales
let handler = VNImageRequestHandler(cgImage: cg, options: [:])
do {
    try handler.perform([request])
} catch {
    fail("Apple Vision recognition error: \(error)")
}
let observations = request.results ?? []
var lines: [[String: Any]] = []
for observation in observations {
    guard let best = observation.topCandidates(1).first else { continue }
    let box = observation.boundingBox
    lines.append([
        "text": best.string,
        "confidence": Double(best.confidence),
        "x": Double(box.minX),
        // Vision uses bottom-left origin; normalize to top-left.
        "y": Double(1.0 - box.maxY),
        "width": Double(box.width),
        "height": Double(box.height)
    ])
}
lines.sort {
    let ay = $0["y"] as? Double ?? 0
    let by = $1["y"] as? Double ?? 0
    if abs(ay - by) > 0.006 { return ay < by }
    return ($0["x"] as? Double ?? 0) < ($1["x"] as? Double ?? 0)
}
do {
    let data = try JSONSerialization.data(withJSONObject: ["lines": lines], options: [.sortedKeys])
    guard let jsonText = String(data: data, encoding: .utf8) else {
        fail("Could not encode OCR JSON")
    }
    print(jsonText)
} catch {
    fail("Apple Vision JSON error: \(error)")
}
