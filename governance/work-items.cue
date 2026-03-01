package workitems

// Work-items schema for L2 (project-level) tracking.
// Self-contained - no external dependencies.
//
// PURPOSE:
// L2 work-items track project-specific work (features, bugs, improvements).
// Single-repo scope - simpler than L1/L2 schemas.
//
// NOT operational - this is a planning/tracking artifact.
// Projects may also use git issues, milestones, or FCOS work-items.
//
// States: triage | queued | doing | review | done

#State: "triage" | "queued" | "doing" | "review" | "done"

#Task: {
	text: string
	done: bool
}

#Issue: {
	id:           string
	title:        string
	state:        #State
	labels:       [...string]
	tasks:        [...#Task]
	dod:          string
	assignee?:    string
	completed_at?: string & =~"^[0-9]{4}-[0-9]{2}-[0-9]{2}$"
	note?:        string
}

#Milestone: {
	id:     string & =~"^[A-Z]?[0-9]+$"
	title:  string
	issues: [...#Issue]
}

#WorkItems: {
	schema_version: 1
	updated_at:     string & =~"^[0-9]{4}-[0-9]{2}-[0-9]{2}$"
	owner:          string
	project_name:   string

	milestones: [...#Milestone]
}
