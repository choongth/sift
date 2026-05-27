import asyncio


async def confirm_write_report(
    title: str,
    filename: str,
    executive_summary: str,
    key_findings: list[str],
    confidence: str,
) -> bool:
    findings_preview = "\n".join(f"    • {f}" for f in key_findings[:5])
    if len(key_findings) > 5:
        findings_preview += f"\n    ... and {len(key_findings) - 5} more"

    print("\n" + "═" * 60)
    print("  HUMAN CONFIRMATION REQUIRED")
    print("═" * 60)
    print(f"  Title      : {title}")
    print(f"  Filename   : {filename}")
    print(f"  Confidence : {confidence}")
    print(f"\n  Summary    : {executive_summary}")
    print(f"\n  Key findings:\n{findings_preview}")
    print("═" * 60)

    answer = await asyncio.to_thread(input, "\nWrite this report? [yes/no]: ")
    return answer.strip().lower() == "yes"
