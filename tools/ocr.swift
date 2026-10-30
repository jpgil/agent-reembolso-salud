import Foundation
import Vision
import AppKit
import PDFKit

guard CommandLine.arguments.count > 1 else {
    print("Usage: ocr <file-path>")
    exit(1)
}

let filePath = CommandLine.arguments[1]
let fileURL = URL(fileURLWithPath: filePath)

func recognizeText(in cgImage: CGImage) {
    let requestHandler = VNImageRequestHandler(cgImage: cgImage, options: [:])
    let request = VNRecognizeTextRequest { (request, error) in
        if let error = error {
            print("Error during text recognition: \(error.localizedDescription)")
            return
        }
        guard let observations = request.results as? [VNRecognizedTextObservation] else { return }
        for observation in observations {
            guard let candidate = observation.topCandidates(1).first else { continue }
            print(candidate.string)
        }
    }
    request.recognitionLevel = .accurate
    request.recognitionLanguages = ["es-CL", "es", "en-US", "en"]
    try? requestHandler.perform([request])
}

if fileURL.pathExtension.lowercased() == "pdf" {
    guard let pdf = PDFDocument(url: fileURL) else {
        print("Error: Could not load PDF at \(filePath)")
        exit(1)
    }
    for pageIndex in 0..<pdf.pageCount {
        guard let page = pdf.page(at: pageIndex) else { continue }
        if let text = page.string, !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            print(text)
        } else {
            let pageRect = page.bounds(for: .mediaBox)
            let image = NSImage(size: pageRect.size, flipped: false) { rect in
                guard let context = NSGraphicsContext.current?.cgContext else { return false }
                page.draw(with: .mediaBox, to: context)
                return true
            }
            guard let tiffData = image.tiffRepresentation,
                  let bitmap = NSBitmapImageRep(data: tiffData),
                  let cgImage = bitmap.cgImage else { continue }
            recognizeText(in: cgImage)
        }
    }
} else {
    guard let image = NSImage(contentsOf: fileURL) else {
        print("Error: Could not load image at \(filePath)")
        exit(1)
    }
    guard let tiffData = image.tiffRepresentation,
          let bitmap = NSBitmapImageRep(data: tiffData),
          let cgImage = bitmap.cgImage else {
        print("Error: Could not create CGImage from \(filePath)")
        exit(1)
    }
    recognizeText(in: cgImage)
}
