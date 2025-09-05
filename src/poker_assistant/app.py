from poker_assistant.ui.room_selector import choose_table

cand = choose_table(room_pref=None)  # 'winamax' | 'pmu' | None
if not cand:
    print("Aucune table détectée")
    raise SystemExit(1)

print(f"Table choisie: {cand.room_guess} - {cand.title} - bbox={cand.bbox}")
# Vous pouvez ensuite brancher capture/OCR avec cand.bbox
