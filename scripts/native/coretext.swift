// Native CoreText shaping and PNG output. No browser / HarfBuzz involved.
import Foundation
import CoreText
import CoreGraphics
import ImageIO
import UniformTypeIdentifiers

func require(_ ok: Bool, _ message: String) throws {
    if !ok { throw NSError(domain: "NativeProof", code: 1, userInfo: [NSLocalizedDescriptionKey: message]) }
}
func render() throws {
    try require(CommandLine.arguments.count == 6, "font, cases, output, family, weight required")
    let args = CommandLine.arguments
    let url = URL(fileURLWithPath: args[1])
    guard let provider = CGDataProvider(url: url as CFURL), let cgFont = CGFont(provider) else {
        throw NSError(domain: "NativeProof", code: 2)
    }
    let baseFont = CTFontCreateWithGraphicsFont(cgFont, 24, nil, nil)
    let contents = try String(contentsOfFile: args[2], encoding: .utf8)
    for line in contents.split(separator: "\n") {
        let columns = line.split(separator: "\t", omittingEmptySubsequences: false).map(String.init)
        try require(columns.count == 6, "bad cases.tsv row")
        let id = columns[0], vertical = columns[2] == "1"
        var features: [[String: Any]] = []
        for (index, tag) in [(3, "kern"), (4, "locl")] where columns[index] != "-1" {
            features.append([kCTFontOpenTypeFeatureTag as String: tag, kCTFontOpenTypeFeatureValue as String: Int(columns[index])!])
        }
        let descriptor = CTFontDescriptorCreateWithAttributes([kCTFontFeatureSettingsAttribute as String: features] as CFDictionary)
        let font = CTFontCreateCopyWithAttributes(baseFont, 24, nil, descriptor)
        var attributes: [NSAttributedString.Key: Any] = [
            NSAttributedString.Key(kCTFontAttributeName as String): font,
            NSAttributedString.Key(kCTLanguageAttributeName as String): columns[1],
            NSAttributedString.Key(kCTVerticalFormsAttributeName as String): vertical,
        ]
        // CoreText's zero kern attribute explicitly disables kerning; absence uses font defaults.
        if columns[3] == "0" { attributes[NSAttributedString.Key(kCTKernAttributeName as String)] = 0 }
        let text = NSAttributedString(string: columns[5], attributes: attributes)
        let setter = CTFramesetterCreateWithAttributedString(text as CFAttributedString)
        let path = CGPath(rect: CGRect(x: 40, y: 40, width: 1520, height: 820), transform: nil)
        let options = [kCTFrameProgressionAttributeName as String: vertical ? CTFrameProgression.rightToLeft.rawValue : CTFrameProgression.topToBottom.rawValue]
        let frame = CTFramesetterCreateFrame(setter, CFRange(location: 0, length: 0), path, options as CFDictionary)
        try require(CTFrameGetVisibleStringRange(frame).length == text.length, "clipped frame: \(id)")
        guard let context = CGContext(data: nil, width: 1600, height: 900, bitsPerComponent: 8, bytesPerRow: 0,
                                      space: CGColorSpaceCreateDeviceRGB(), bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue) else {
            throw NSError(domain: "NativeProof", code: 3)
        }
        context.setFillColor(CGColor(gray: 1, alpha: 1)); context.fill(CGRect(x: 0, y: 0, width: 1600, height: 900))
        context.setFillColor(CGColor(gray: 0, alpha: 1)); context.textMatrix = .identity
        CTFrameDraw(frame, context)
        var runs: [[String: Any]] = []
        for ctLine in CTFrameGetLines(frame) as! [CTLine] {
            for run in CTLineGetGlyphRuns(ctLine) as! [CTRun] {
                let count = CTRunGetGlyphCount(run)
                var glyphs = [CGGlyph](repeating: 0, count: count)
                var advances = [CGSize](repeating: .zero, count: count)
                var positions = [CGPoint](repeating: .zero, count: count)
                CTRunGetGlyphs(run, CFRange(location: 0, length: 0), &glyphs)
                CTRunGetAdvances(run, CFRange(location: 0, length: 0), &advances)
                CTRunGetPositions(run, CFRange(location: 0, length: 0), &positions)
                let runAttrs = CTRunGetAttributes(run) as NSDictionary
                let actual = runAttrs[kCTFontAttributeName as String] as! CTFont
                runs.append(["font": CTFontCopyPostScriptName(actual) as String, "glyphs": glyphs.map(Int.init),
                             "advances": advances.map { [$0.width, $0.height] },
                             "positions": positions.map { [$0.x, $0.y] }])
            }
        }
        let prefix = URL(fileURLWithPath: args[3]).appendingPathComponent(id)
        let record: [String: Any] = ["engine": "coretext", "sample": id, "vertical": vertical, "emSize": 24,
                                     "os": ProcessInfo.processInfo.operatingSystemVersionString, "runs": runs]
        try JSONSerialization.data(withJSONObject: record, options: [.prettyPrinted, .sortedKeys])
            .write(to: prefix.appendingPathExtension("json"))
        guard let image = context.makeImage(), let dest = CGImageDestinationCreateWithURL(
            prefix.appendingPathExtension("png") as CFURL, UTType.png.identifier as CFString, 1, nil) else {
            throw NSError(domain: "NativeProof", code: 4)
        }
        CGImageDestinationAddImage(dest, image, nil)
        try require(CGImageDestinationFinalize(dest), "PNG write failed")
    }
}
do { try render() } catch { fputs("CoreText proof failed: \(error)\n", stderr); exit(1) }
