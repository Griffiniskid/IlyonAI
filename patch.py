with open("src/api/routes/intel.py", "r") as f:
    content = f.read()

content = content.replace('    return web.json_response({\n        "incidents": incidents,\n        "count": len(incidents),\n        "total_stolen_usd": total_stolen,\n        "filters": {\n            "chain": chain,\n            "attack_type": attack_type,\n            "min_amount": min_amount,\n            "search": search,\n        },\n    })', '''    return web.json_response({
        "incidents": incidents,
        "count": len(incidents),
        "total_stolen_usd": total_stolen,
        "filters": {
            "chain": chain,
            "attack_type": attack_type,
            "min_amount": min_amount,
            "search": search,
        },
        "meta": {
            "cursor": None,
            "freshness": "warm"
        }
    })''')

with open("src/api/routes/intel.py", "w") as f:
    f.write(content)
