function(doc) {
    if (doc.type == "api_user") {
    	// emit one row for every registered item
        for (var alias in doc.registered_items) {
           emit([doc.registered_items[alias]["tiid"]], [alias, doc.current_key.toLowerCase()]);
        }
    }
}
